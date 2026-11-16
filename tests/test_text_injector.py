from voice_agent.inject.text_injector import TextInjector


class FakeClipboard:
    def __init__(self, text=None):
        self.text = text

    def get_text(self):
        return self.text

    def set_text(self, text):
        self.text = text


class FakeKeyboard:
    def __init__(self, clipboard):
        self.clipboard = clipboard
        self.pasted = []
        self.released = []

    def release_keys(self, tokens):
        self.released.append(set(tokens))

    def paste(self):
        self.pasted.append(self.clipboard.text)


def make(previous="old", **kw):
    cb = FakeClipboard(previous)
    kb = FakeKeyboard(cb)
    scheduled = []
    inj = TextInjector(cb, kb, schedule=lambda ms, fn: scheduled.append(fn),
                       sleep=lambda s: None, **kw)
    return inj, cb, kb, scheduled


def test_paste_and_restore():
    inj, cb, kb, scheduled = make()
    assert inj.inject("Hello world.")
    assert kb.pasted == ["Hello world. "]
    assert cb.text == "Hello world. "
    scheduled[0]()
    assert cb.text == "old"


def test_empty_text_not_pasted():
    inj, cb, kb, scheduled = make()
    assert not inj.inject("   ")
    assert kb.pasted == [] and cb.text == "old"


def test_no_restore_when_user_copied_meanwhile():
    inj, cb, kb, scheduled = make()
    inj.inject("Hi")
    cb.text = "user copy"
    scheduled[0]()
    assert cb.text == "user copy"


def test_options():
    inj, cb, kb, scheduled = make(restore_clipboard=False, append_space=False)
    inj.inject("Hi")
    assert kb.pasted == ["Hi"] and scheduled == []


def test_waits_for_keys_released():
    held = iter([{"win"}, {"win"}, set()])
    inj, cb, kb, _ = make(held_keys=lambda: next(held, set()))
    inj.inject("x")
    assert kb.released == [] and kb.pasted == ["x "]


def test_releases_still_held_modifiers_after_timeout():
    inj, cb, kb, _ = make(held_keys=lambda: {"win", "ctrl"}, release_wait=0.0)
    inj.inject("x")
    assert kb.released == [{"win", "ctrl"}]
    assert kb.pasted == ["x "]
