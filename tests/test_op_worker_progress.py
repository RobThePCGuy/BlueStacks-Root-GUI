from views.main_window import _OpWorker


def test_op_worker_progress_emits_text_and_percent(qapp):
    worker = _OpWorker(lambda progress: (progress("halfway", 50), "done")[-1])
    received = []
    worker.progress.connect(lambda msg, pct: received.append((msg, pct)))
    worker.run()
    assert received == [("halfway", 50)]


def test_op_worker_progress_accepts_unknown_percent(qapp):
    worker = _OpWorker(lambda progress: (progress("working", -1), "done")[-1])
    received = []
    worker.progress.connect(lambda msg, pct: received.append((msg, pct)))
    worker.run()
    assert received == [("working", -1)]
