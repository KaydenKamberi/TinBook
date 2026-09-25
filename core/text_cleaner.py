"""Gutenberg text cleaning functions owned by CP1C."""


def strip_gutenberg_boilerplate(raw: str) -> str:
    """Remove Project Gutenberg boilerplate. Implemented by CP1C."""
    raise NotImplementedError


def clean_for_speech(text: str) -> str:
    """Normalize text for speech synthesis. Implemented by CP1C."""
    raise NotImplementedError


def clean(raw: str) -> str:
    """Strip boilerplate and normalize text for speech. Implemented by CP1C."""
    raise NotImplementedError