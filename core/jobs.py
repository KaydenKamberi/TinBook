"""Audio generation queue owned by CP1A."""


class JobQueue:
    """Single-worker chapter generation queue owned by CP1A."""

    def start(self) -> None:
        """Start the worker and resume unfinished books. Implemented by CP1A."""
        raise NotImplementedError

    def enqueue(self, book_id: str) -> None:
        """Add a book to the generation queue. Implemented by CP1A."""
        raise NotImplementedError

    def status(self) -> dict:
        """Return current and queued book-generation status. Implemented by CP1A."""
        raise NotImplementedError

    def stop(self) -> None:
        """Stop the worker. Implemented by CP1A."""
        raise NotImplementedError


def get_queue() -> JobQueue:
    """Return the process-wide queue singleton. Implemented by CP1A."""
    raise NotImplementedError