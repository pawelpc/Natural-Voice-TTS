"""Spoken emphasis for **bold**, *italic* and ALL-CAPS words (Paul, Phase 4 note #13).

On by default since Paul approved the prototype (EMPHASIS_ENABLED; set it False to
read emphasized words plain). Kokoro has no emphasis input, so the span is
changed inside Kokoro's own single forward pass, with the same weights:
  - duration: the span's phonemes get a lower speed (Kokoro divides each
    phoneme's predicted duration by `speed`, which may be a per-phoneme tensor);
  - pitch: Kokoro's predicted F0 curve is scaled over the span, with ramps;
  - loudness: a gain envelope on the audio over the span, with ramps.
One call, so there is no seam and the rest of the sentence keeps its prosody.
Evidence and the options that were rejected: tests/emphasis/FINDINGS.md.

The normalizer marks spans with OPEN/CLOSE sentinels while it rewrites the
text; extract() removes them and returns character spans for synthesis.
"""

import logging
import re
import sys
import threading

import numpy as np

logger = logging.getLogger(__name__)

EMPHASIS_ENABLED = True      # Paul listened (tests/emphasis/listen.html) and kept it as prototyped, 2026-10-22

# --- Strength (moderate; "strong" in the findings was 0.80 / 1.15 / 3.0) ---
EMPHASIS_DURATION = 0.85     # speed on the span's phonemes (measured: span about 20% longer, FINDINGS.md)
EMPHASIS_PITCH = 1.10        # F0 scale on the span (measured: about +8% pitch, about 1.3 semitones)
EMPHASIS_GAIN_DB = 2.0       # loudness on the span
EMPHASIS_MAX_WORDS = 5       # a longer bold/italic span (a whole bold sentence) is read plain

PITCH_RAMP_FRAMES = 4        # F0 eases in and out over 4 alignment frames (100 ms)
GAIN_RAMP_FRAMES = 2         # gain eases in and out over 2 frames (50 ms)
FRAME_SAMPLES = 600          # one Kokoro alignment frame at 24 kHz (25 ms)

OPEN, CLOSE = '', ''   # private-use characters: never in real text, not \w
MARKERS = OPEN + CLOSE

# An ALL-CAPS word that isn't part of a file name, path, flag or identifier, nor right
# after a number ("4 PM", "8 GB").
CAPS_RE = re.compile(r"(?<![\w.\\/@$%\-])(?<!\d )([A-Z]{2,}(?:'[A-Z]+)?)(?![\w\\/@%\-]|\.\w)")
ROMAN_NUMERAL_RE = re.compile(r'[IVXLCDM]+')
LOWER_WORD_RE = re.compile(r'\b[a-z]{2,}\b')


_golds_cache: dict | None = None
_golds_lock = threading.Lock()


def _golds() -> dict:
    """misaki's main US English dictionary (the one Kokoro reads words from).

    Reuses the dictionary the running Kokoro pipeline already holds. Building a
    second copy takes about 2.7 s (178,646 entries), and that used to land on
    the first read with an ALL-CAPS word after the app started. Only without a
    pipeline (unit tests, no model) is a copy loaded, once.
    """
    global _golds_cache
    with _golds_lock:
        if _golds_cache is None:
            engine = sys.modules.get('tts_engine')
            pipeline = getattr(engine, '_pipeline', None)
            lexicon = getattr(getattr(pipeline, 'g2p', None), 'lexicon', None)
            if lexicon is not None and getattr(lexicon, 'british', True) is False:
                _golds_cache = lexicon.golds
            else:
                from misaki import en
                logger.info("Loading misaki's dictionary for emphasis (no Kokoro pipeline yet)")
                _golds_cache = en.Lexicon(british=False).golds
        return _golds_cache


def is_emphatic_caps(word: str) -> bool:
    """ "NOT", "NEVER", "DON'T" yes; "API", "GPU", "IT", "US", "SKILL", "XVI" no.

    misaki spells a capitalized word letter by letter when the dictionary has it
    in capitals (an acronym); a word it only knows in lower case is a shouted word.
    """
    if ROMAN_NUMERAL_RE.fullmatch(word):
        return False
    golds = _golds()
    return word not in golds and word.lower() in golds


def mark_caps(text: str) -> str:
    """Wrap emphatic ALL-CAPS words in OPEN/CLOSE. A line that is all capitals is shouting, not emphasis."""
    if not LOWER_WORD_RE.search(text):
        return text
    return CAPS_RE.sub(lambda m: f'{OPEN}{m.group(1)}{CLOSE}' if is_emphatic_caps(m.group(1)) else m.group(0), text)


def strip_markers(text: str) -> str:
    return text.replace(OPEN, '').replace(CLOSE, '')


def extract(text: str) -> tuple[str, tuple[tuple[int, int], ...]]:
    """Remove the sentinels; return the plain text and the emphasized (start, end) spans in it.

    Nested or unbalanced markers collapse to the outermost span. Spans longer than
    EMPHASIS_MAX_WORDS words, or with no letters or digits, are dropped.
    """
    if OPEN not in text and CLOSE not in text:
        return text, ()
    out, spans, depth, start = [], [], 0, 0
    for ch in text:
        if ch == OPEN:
            if depth == 0:
                start = len(out)
            depth += 1
        elif ch == CLOSE:
            if depth > 0:
                depth -= 1
                if depth == 0:
                    spans.append((start, len(out)))
        else:
            out.append(ch)
    plain = ''.join(out)
    kept = []
    for a, b in spans:
        # Trim spaces and punctuation at the edges ("**Bottom line:**" -> "Bottom line").
        while a < b and not plain[a].isalnum():
            a += 1
        while b > a and not plain[b - 1].isalnum():
            b -= 1
        if a < b and len(plain[a:b].split()) <= EMPHASIS_MAX_WORDS:
            kept.append((a, b))
    return plain, tuple(kept)


# --- Synthesis -------------------------------------------------------------------

def token_flags(text: str, tokens: list, spans) -> list[bool]:
    """Which misaki tokens fall inside a span, matching each token's text in order."""
    flags, pos = [], 0
    for t in tokens:
        at = text.find(t.text, pos) if t.text else -1
        if at < 0:
            flags.append(False)
            continue
        pos = at + len(t.text)
        flags.append(bool(t.phonemes) and any(at < b and pos > a for a, b in spans))
    return flags


def phoneme_mask(ps: str, tks: list, flags: list[bool], vocab: dict) -> list[bool] | None:
    """One flag per model input id of `ps` (BOS/EOS excluded), or None if ps can't be matched.

    Rebuilds ps the way KPipeline.tokens_to_ps joins tokens, keeping each character's flag;
    the space between two emphasized words is emphasized too.
    """
    chars: list[tuple[str, bool]] = []
    for k, t in enumerate(tks):
        chars.extend((c, flags[k]) for c in t.phonemes)
        if t.whitespace:
            chars.append((' ', flags[k] and k + 1 < len(tks) and flags[k + 1]))
    while chars and chars[0][0] == ' ':
        chars.pop(0)
    while chars and chars[-1][0] == ' ':
        chars.pop()
    if ''.join(c for c, _ in chars)[:len(ps)] != ps:
        return None
    return [f for c, f in chars[:len(ps)] if vocab.get(c) is not None]


def _envelope(frames: np.ndarray, ramp: int, per_frame: int, length: int) -> np.ndarray:
    """0/1 per alignment frame -> a smooth 0..1 curve with `per_frame` values per frame.

    A plateau over the emphasized frames with linear ramps `ramp` frames long,
    interpolated between frame centres, so nothing changes in a step.
    """
    w = frames.astype(np.float64)
    if ramp > 1:
        w = np.clip(np.convolve(w, np.ones(ramp) / ramp, mode='same'), 0, 1)
    centres = np.arange(len(w)) * per_frame + (per_frame - 1) / 2
    return np.interp(np.arange(length), centres, w).astype(np.float32)


def _span_rounding(duration, m):
    """Frames per phoneme: Kokoro's rounding outside the span; inside it, cumulative
    rounding, so the span really gets 1/EMPHASIS_DURATION longer. (Rounding each short
    phoneme on its own often cancels a 15% change: 1.9 frames / 0.85 is still 2.)"""
    import torch
    pred = torch.round(duration).clamp(min=1)
    on = m[0] > 0
    k = 0
    while k < len(on):
        if not on[k]:
            k += 1
            continue
        j = k
        while j < len(on) and on[j]:
            j += 1
        edges = torch.round(torch.cumsum(duration[0, k:j], 0))
        pred[0, k:j] = torch.diff(edges, prepend=edges.new_zeros(1)).clamp(min=1)
        k = j
    return pred.long().squeeze()


def forward(model, ps: str, ref_s, mask: list[bool], speed: float):
    """KModel.forward_with_tokens (kokoro 0.9.4) with emphasis on the masked phonemes.

    Same weights and steps as Kokoro's own forward. Returns (audio as a numpy array,
    pred_dur, one 0/1 value per alignment frame telling which frames are emphasized).
    """
    import torch
    ids = [model.vocab[p] for p in ps if model.vocab.get(p) is not None]
    if len(ids) != len(mask):
        raise ValueError(f'emphasis mask has {len(mask)} flags for {len(ids)} phonemes')
    device = model.device
    input_ids = torch.LongTensor([[0, *ids, 0]]).to(device)
    ref_s = ref_s.to(device)
    m = torch.tensor([[0.0, *[1.0 if f else 0.0 for f in mask], 0.0]], device=device)
    speeds = speed * (1.0 + m * (EMPHASIS_DURATION - 1.0))
    with torch.no_grad():
        n = input_ids.shape[-1]
        input_lengths = torch.full((1,), n, device=device, dtype=torch.long)
        text_mask = torch.zeros((1, n), dtype=torch.bool, device=device)
        bert_dur = model.bert(input_ids, attention_mask=(~text_mask).int())
        d_en = model.bert_encoder(bert_dur).transpose(-1, -2)
        s = ref_s[:, 128:]
        d = model.predictor.text_encoder(d_en, s, input_lengths, text_mask)
        x, _ = model.predictor.lstm(d)
        duration = torch.sigmoid(model.predictor.duration_proj(x)).sum(axis=-1) / speeds
        pred_dur = _span_rounding(duration, m)
        indices = torch.repeat_interleave(torch.arange(n, device=device), pred_dur)
        aln = torch.zeros((n, indices.shape[0]), device=device)
        aln[indices, torch.arange(indices.shape[0])] = 1
        aln = aln.unsqueeze(0)
        en = d.transpose(-1, -2) @ aln
        F0_pred, N_pred = model.predictor.F0Ntrain(en, s)
        frames = m[0][indices].cpu().numpy()
        if EMPHASIS_PITCH != 1.0 and frames.any():
            w = _envelope(frames, PITCH_RAMP_FRAMES, 2, F0_pred.shape[-1])  # 2 F0 values per frame
            F0_pred = F0_pred * (1.0 + torch.tensor(w, device=device) * (EMPHASIS_PITCH - 1.0))
        t_en = model.text_encoder(input_ids, input_lengths, text_mask)
        audio = model.decoder(t_en @ aln, F0_pred, N_pred, ref_s[:, :128]).squeeze()
    return audio.cpu().numpy(), pred_dur.cpu(), frames


def apply_gain(audio: np.ndarray, frames: np.ndarray) -> np.ndarray:
    """Raise the emphasized frames by EMPHASIS_GAIN_DB, easing in and out."""
    if EMPHASIS_GAIN_DB == 0 or not frames.any():
        return audio
    env = _envelope(frames, GAIN_RAMP_FRAMES, FRAME_SAMPLES, len(audio))
    out = audio * (1.0 + env * (10 ** (EMPHASIS_GAIN_DB / 20) - 1.0))
    return np.clip(out, -1.0, 1.0).astype(np.float32)


def synthesize(pipeline, text: str, spans, voice: str, speed: float, split_pattern: str):
    """Like KPipeline.__call__ for English, with emphasis on `spans` (character ranges of text).

    Yields (graphemes, audio tensor, tokens with start_ts/end_ts), as the pipeline does.
    """
    import torch
    from kokoro import KPipeline

    model = pipeline.model
    pack = pipeline.load_voice(voice).to(model.device)
    text = text.strip()
    pos = 0
    for piece in re.split(f'({split_pattern})', text):
        start, pos = pos, pos + len(piece)
        if not piece.strip() or re.fullmatch(split_pattern, piece):
            continue
        local = [(max(a, start) - start, min(b, pos) - start) for a, b in spans if a < pos and b > start]
        _, tokens = pipeline.g2p(piece)
        flags = dict(zip(map(id, tokens), token_flags(piece, tokens, local)))
        for graphemes, ps, tks in pipeline.en_tokenize(tokens):
            if not ps:
                continue
            ps = ps[:510]
            mask = phoneme_mask(ps, tks, [flags.get(id(t), False) for t in tks], model.vocab)
            if mask is None:  # can't line the flags up with the phonemes: read it plain
                logger.warning("Emphasis skipped, phonemes didn't match tokens: %.60s", graphemes)
                mask = [False] * sum(1 for p in ps if model.vocab.get(p) is not None)
            audio, pred_dur, frames = forward(model, ps, pack[len(ps) - 1], mask, speed)
            audio = apply_gain(audio, frames)
            KPipeline.join_timestamps(tks, pred_dur)
            yield graphemes, torch.from_numpy(audio), tks
