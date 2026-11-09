"""Rebuild models/categories.npy after editing app/ai/categories.py.

Needs the CLIP text model once (~250 MB):  bash scripts/get_clip_text_model.sh
Run from the project folder:              python -m tools.build_categories
"""
import numpy as np
import onnxruntime as ort

from app.ai.categories import CATEGORIES
from app.ai.clip_tok import Tokenizer
from app.config import settings

sess = ort.InferenceSession(str(settings.MODELS_DIR / "clip_textual.onnx"), providers=["CPUExecutionProvider"])
ids, mask = Tokenizer().batch(["a photo of " + c[2] + ", 3d printed plastic" for c in CATEGORIES])
emb = sess.run(None, {"input_ids": ids, "attention_mask": mask})[0]
emb = emb / np.linalg.norm(emb, axis=1, keepdims=True)
np.save(settings.MODELS_DIR / "categories.npy", emb.astype(np.float32))
print("ok:", len(CATEGORIES), "categories")
