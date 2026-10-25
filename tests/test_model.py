import json

from storyteller.model import OutlineEntry, Script, Sentence, SpokenWord, Word


def test_script_roundtrip():
    display = [Word("p²", 0, (10.0, 20.0, 18.0, 30.0)), Word("x", 0, (20.0, 20.0, 26.0, 30.0))]
    sentence = Sentence(
        id="s00000",
        block_id="b000_000",
        spoken=[SpokenWord("p", 0), SpokenWord("squared", 0)],
        display=display,
        pause_after_ms=250,
        kind="body",
    )
    s = Script(
        pack_id="abc",
        profile="studypack",
        title="T",
        sentences=[sentence],
        outline=[OutlineEntry(level=2, title="1 Chunk", page=0, y=72.5, sentence_id="s00000")],
        page_count=1,
    )
    assert Script.from_dict(json.loads(json.dumps(s.to_dict()))) == s
    assert sentence.spoken_text == "p squared"
