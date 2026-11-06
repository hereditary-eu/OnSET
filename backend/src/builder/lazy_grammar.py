"""Greedy grammar-constrained sampling that checks the grammar lazily.

llama-cpp-python samples with a grammar by running the grammar over the whole
vocabulary (65k tokens for LFM2) on the CPU for every generated token, which
takes several times longer than the model's forward pass on a GPU. With greedy
sampling most of that work is wasted: the sampled token is the most likely
token the grammar allows, which usually is just the most likely token.

``LazyGreedyGrammarSampler`` therefore checks only the argmax token against the
grammar and runs the grammar over the whole vocabulary only when it rejects that
token (as llama.cpp's own ``common_sampler`` does). The result is the same as
stock greedy sampling with a grammar: if the grammar allows the overall argmax,
it is also the argmax of the allowed tokens (ties go to the lowest token id in
both), and otherwise the full check is exactly the stock computation.

This module imports llama.cpp, so import it only where a model is loaded.
"""

import ctypes

import llama_cpp
import numpy as np
from llama_cpp import Llama, LlamaGrammar

# numpy view of llama_token_data {int32 id; float logit; float p}
TOKEN_DATA_DTYPE = np.dtype([("id", np.intc), ("logit", np.single), ("p", np.single)], align=True)


class LazyGreedyGrammarSampler:
    """Greedy sampling with a grammar, checking the whole vocabulary only when needed.

    Implements the part of ``llama_cpp._internals.LlamaSampler`` that ``Llama`` uses
    (``sample``, which also advances the grammar by the sampled token)."""

    def __init__(self, llm: Llama, grammar: LlamaGrammar):
        self.n_vocab = llm.n_vocab()
        self.grammar = llama_cpp.llama_sampler_init_grammar(
            llm._model.vocab, grammar._grammar.encode("utf-8"), grammar._root.encode("utf-8")
        )
        # candidate buffers, reused for every token: the argmax alone and the whole vocabulary
        self._one = (llama_cpp.llama_token_data * 1)()
        self._all = (llama_cpp.llama_token_data * self.n_vocab)()
        self._all_np = np.ctypeslib.as_array(self._all).view(TOKEN_DATA_DTYPE)

    def _apply_grammar(self, candidates, size: int):
        """Set the logit of every candidate the grammar rejects to -inf."""
        array = llama_cpp.llama_token_data_array(data=candidates, size=size, selected=-1, sorted=False)
        llama_cpp.llama_sampler_apply(self.grammar, ctypes.byref(array))

    def sample(self, ctx, idx: int = -1) -> int:
        logits = np.ctypeslib.as_array(llama_cpp.llama_get_logits_ith(ctx.ctx, idx), shape=(self.n_vocab,))
        token = int(np.argmax(logits))
        self._one[0].id, self._one[0].logit, self._one[0].p = token, float(logits[token]), 0.0
        self._apply_grammar(self._one, 1)
        if not np.isfinite(self._one[0].logit):
            # the argmax is not allowed here: constrain the whole vocabulary, as stock sampling does
            self._all_np["id"] = np.arange(self.n_vocab)
            self._all_np["logit"] = logits
            self._apply_grammar(self._all, self.n_vocab)
            token = int(self._all_np["id"][np.argmax(self._all_np["logit"])])
        llama_cpp.llama_sampler_accept(self.grammar, token)
        return token

    def close(self):
        if self.grammar is not None:
            llama_cpp.llama_sampler_free(self.grammar)
            self.grammar = None

    def __del__(self):
        self.close()


class LazyGrammarLlama(Llama):
    """``Llama`` that samples greedy generations with a grammar by ``LazyGreedyGrammarSampler``
    (same output, faster); any other sampling setup uses the stock sampler."""

    def _init_sampler(self, **params):
        greedy = (
            params.get("temp") == 0.0
            and params.get("logits_processor") is None
            and params.get("repeat_penalty", 1.0) == 1.0
            and not params.get("frequency_penalty")
            and not params.get("presence_penalty")
        )
        if greedy and params.get("grammar") is not None:
            return LazyGreedyGrammarSampler(self, params["grammar"])
        return super()._init_sampler(**params)
