"""Writes the tiny e-mail text set of the end-to-end test (texts/mails/*.txt), with deliberately
variant names of the same entities so the builder's disambiguation has something to merge."""

from pathlib import Path

MAILS = [
    ("jeff.skilling@enron.com", "Q3 results",
     "Jeff Skilling, CEO of Enron Corp, presented the third quarter results to the board in Houston. "
     "Kenneth Lay chaired the meeting."),
    ("kenneth.lay@enron.com", "Leadership",
     "Jeffrey Skilling will remain chief executive of Enron Corporation. Ken Lay thanked Andrew Fastow "
     "for the finance work."),
    ("andrew.fastow@enron.com", "LJM partnership",
     "Andy Fastow, CFO of enron corp., set up the LJM partnership. Arthur Andersen audited the accounts of Enron."),
    ("sherron.watkins@enron.com", "Accounting concerns",
     "Sherron Watkins wrote to Kenneth Lay that Enron Corp. may implode in a wave of accounting scandals. "
     "She mentioned Andrew Fastow and Arthur Andersen LLP."),
    ("news@dynegy.com", "Merger talks",
     "Dynegy Inc. is in merger talks with Enron Corporation. Chuck Watson of Dynegy met Kenneth L. Lay "
     "and Jeff Skilling."),
    ("greg.whalley@enron.com", "Trading update",
     "Greg Whalley, president of Enron Corp, told traders that Jeffrey K. Skilling resigned. "
     "Dynegy Inc will provide liquidity."),
    ("louise.kitchen@enron.com", "EnronOnline",
     "Louise Kitchen launched EnronOnline for Enron Corporation. Greg Whalley and Jeff Skilling "
     "supported the project."),
    ("vince.kaminski@enron.com", "Research group",
     "Vince Kaminski leads research at Enron Corp. He warned Andrew S. Fastow about the LJM risk. "
     "Arthur Andersen reviewed the memo."),
]

out = Path(__file__).resolve().parent / "texts" / "mails"
out.mkdir(parents=True, exist_ok=True)
for i, (sender, subject, body) in enumerate(MAILS, 1):
    (out / f"{i:02d}.txt").write_text(f"From: {sender}\nTo: staff@enron.com\nSubject: {subject}\n\n{body}\n")
print(f"wrote {len(MAILS)} mails to {out}")
