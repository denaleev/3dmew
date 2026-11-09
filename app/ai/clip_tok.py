"""Minimal CLIP BPE tokenizer (no torch). Vocabulary: bpe_simple_vocab_16e6.txt.gz from OpenAI CLIP."""
import gzip, os, re
from functools import lru_cache


@lru_cache()
def _bytes_to_unicode():
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
    cs = bs[:]
    n = 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, map(chr, cs)))


class Tokenizer:
    SOT, EOT = "<|startoftext|>", "<|endoftext|>"

    def __init__(self, vocab_path=None):
        vocab_path = vocab_path or os.path.join(os.path.dirname(__file__), "bpe_simple_vocab_16e6.txt.gz")
        merges = gzip.open(vocab_path).read().decode("utf-8").split("\n")[1:49152 - 256 - 2 + 1]
        merges = [tuple(m.split()) for m in merges]
        self.byte_encoder = _bytes_to_unicode()
        vocab = list(self.byte_encoder.values())
        vocab += [v + "</w>" for v in vocab]
        vocab += ["".join(m) for m in merges] + [self.SOT, self.EOT]
        self.encoder = {v: i for i, v in enumerate(vocab)}
        self.ranks = {m: i for i, m in enumerate(merges)}
        self.cache = {}
        self.pat = re.compile(r"'s|'t|'re|'ve|'m|'ll|'d|[^\W\d_]+|\d|[^\s\w]+", re.IGNORECASE)

    def _bpe(self, token):
        if token in self.cache:
            return self.cache[token]
        word = tuple(token[:-1]) + (token[-1] + "</w>",)
        while len(word) > 1:
            pairs = {(word[i], word[i + 1]) for i in range(len(word) - 1)}
            best = min(pairs, key=lambda p: self.ranks.get(p, 1e18))
            if best not in self.ranks:
                break
            first, second = best
            out, i = [], 0
            while i < len(word):
                if i < len(word) - 1 and word[i] == first and word[i + 1] == second:
                    out.append(first + second)
                    i += 2
                else:
                    out.append(word[i])
                    i += 1
            word = tuple(out)
        self.cache[token] = word
        return word

    def encode(self, text):
        text = " ".join(text.lower().split())
        ids = []
        for tok in self.pat.findall(text):
            tok = "".join(self.byte_encoder[b] for b in tok.encode("utf-8"))
            ids += [self.encoder[t] for t in self._bpe(tok)]
        return ids

    def batch(self, texts, length=77):
        import numpy as np
        ids = np.zeros((len(texts), length), np.int32)
        mask = np.zeros((len(texts), length), np.int32)
        for i, t in enumerate(texts):
            toks = [self.encoder[self.SOT]] + self.encode(t)[: length - 2] + [self.encoder[self.EOT]]
            ids[i, : len(toks)] = toks
            mask[i, : len(toks)] = 1
        return ids, mask
