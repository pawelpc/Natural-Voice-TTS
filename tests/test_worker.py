"""Phase 3: the app's worker (app._worker) with a fake engine and player.

Checks the prefetching worker keeps the July behaviour (D2: a failed sentence
is skipped, counted and reported once) and that stop and a following read work.
No model, no sound device. Run: python -m pytest tests -q
"""

import sys
import threading
import time

import numpy as np
import pytest

import harness  # puts src/ on sys.path
import app
import audio_player

WAIT_S = 10


class FakeEngine:
    """Stands in for tts_engine: 100 ms of tone per chunk, optional failures."""

    def __init__(self, fail: tuple[str, ...] = (), delay_s: float = 0.0) -> None:
        self.fail = set(fail)
        self.delay_s = delay_s
        self.calls: list[tuple[str, float]] = []

    def synthesize_segments(self, text: str, voice: str, speed: float):
        self.calls.append((text, time.perf_counter()))
        time.sleep(self.delay_s)
        if any(f in text for f in self.fail):
            raise RuntimeError('synthesis failed')
        t = np.arange(2400) / harness.SAMPLE_RATE
        yield text, (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), []


@pytest.fixture
def worker(monkeypatch):
    """Run app._worker in a thread with fakes; yields a helper to read text and wait."""
    state = {'plays': [], 'notes': [], 'engine': FakeEngine(), 'play_hook': None}
    done = threading.Event()

    def fake_play(audio, sr: int = harness.SAMPLE_RATE) -> bool:
        state['plays'].append((len(audio), time.perf_counter()))
        hook = state['play_hook']
        return hook(len(state['plays'])) if hook else True

    def fake_status(status: str) -> None:
        if status == 'Idle':
            done.set()

    monkeypatch.setitem(sys.modules, 'tts_engine', state['engine'])
    monkeypatch.setattr(app, 'play_audio', fake_play)
    monkeypatch.setattr(app, '_set_status', fake_status)
    monkeypatch.setattr(app, '_notify', lambda title, msg: state['notes'].append(msg))
    monkeypatch.setattr(app.config, 'get', lambda key: {'voice': 'af_heart', 'speed': 1.0}[key])
    thread = threading.Thread(target=app._worker, daemon=True)
    thread.start()

    def read(text: str, engine: FakeEngine | None = None) -> None:
        # The worker imported tts_engine once at start, so reconfigure that same fake.
        if engine is not None:
            state['engine'].fail, state['engine'].delay_s = engine.fail, engine.delay_s
        state['engine'].calls.clear()
        state['plays'].clear()
        state['notes'].clear()
        done.clear()
        app._text_queue.put(text)
        assert done.wait(WAIT_S), 'worker did not finish'

    state['read'] = read
    yield state
    app._text_queue.put(None)
    thread.join(WAIT_S)


def synth_threads_alive() -> bool:
    return any(t.name == 'tts-synth' and t.is_alive() for t in threading.enumerate())


def test_plays_every_chunk_in_order(worker) -> None:
    worker['read']('One. Two. Three.', FakeEngine())
    assert [t for t, _ in worker['engine'].calls] == ['One.', 'Two.', 'Three.']
    assert len(worker['plays']) == 3 and worker['notes'] == []


def test_failed_chunk_is_skipped_and_reported_once(worker) -> None:
    worker['read']('One. Two. Three.', FakeEngine(fail=('Two',)))
    assert len(worker['plays']) == 2
    assert worker['notes'] == ['1 sentence(s) could not be spoken and were skipped.']


def test_stop_ends_the_read_and_the_producer(worker) -> None:
    def stop_on_second(n: int) -> bool:
        if n == 2:
            audio_player.stop()
            return False
        return True
    worker['play_hook'] = stop_on_second
    worker['read']('One. Two. Three. Four. Five. Six.', FakeEngine())
    assert len(worker['plays']) == 2
    deadline = time.time() + WAIT_S
    while synth_threads_alive() and time.time() < deadline:
        time.sleep(0.05)
    assert not synth_threads_alive()
    # A new read after a stop plays in full.
    worker['play_hook'] = None
    worker['read']('Seven. Eight.', FakeEngine())
    assert len(worker['plays']) == 2


def test_next_chunk_is_synthesized_while_current_plays(worker) -> None:
    """Prefetch: chunk 2 is ready before chunk 1 finishes, so no synthesis gap between them."""
    def slow_play(n: int) -> bool:
        time.sleep(0.3)
        return True
    worker['play_hook'] = slow_play
    worker['read']('One. Two. Three.', FakeEngine(delay_s=0.1))
    starts = [t for _, t in worker['plays']]
    second_synth_start = worker['engine'].calls[1][1]
    assert second_synth_start < starts[0] + 0.3          # started while chunk 1 was playing
    assert starts[1] - starts[0] == pytest.approx(0.3, abs=0.08)  # no extra wait for synthesis
