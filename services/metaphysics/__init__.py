"""Metaphysics subsystem — 命理计算核心"""
import os
import logging
from app.config import METAPHYSICS_DIR

logger = logging.getLogger("metaphysics")

# Ensure metaphysics directory exists
os.makedirs(METAPHYSICS_DIR, exist_ok=True)
