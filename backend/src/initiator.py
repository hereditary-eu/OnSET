from abc import ABC
from eval_config import EvalConfig, DBPEDIA_CONFIGS


class Initationatable(ABC):
    def __init__(self):
        super().__init__()
        pass

    def initate(
        self, reset=True, config: EvalConfig = None, force=True, *args, **kwargs
    ):
        pass


class InitatorManager(Initationatable):
    def __init__(self):
        super().__init__()
        self.__initatables: list[tuple[Initationatable, list, dict]] = []

    def register(self, initatable: Initationatable, *args, **kwargs):
        self.__initatables.append((initatable, args, kwargs))

    def initate(self, reset=True, config=DBPEDIA_CONFIGS[0]):
        for (
            initatable,
            args,
            kwargs,
        ) in self.__initatables:
            initatable.initate(reset, config * args, **kwargs)
