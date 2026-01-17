from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.services.exports_worker import run_once


def _make_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
        future=True,
    )

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    return TestingSessionLocal


def test_exports_worker_transitions_to_done_and_sets_artifacts():
    SessionLocal = _make_db()

    with SessionLocal() as db:
        job = models.ExportJob(
            export_id="exp_test_1",
            inputs_hash="0" * 64,
            export_type="state",
            as_of=None,
            filters={"subject_type": "rfq", "subject_id": 123},
            status="queued",
            requested_by_user_id=1,
        )
        db.add(job)
        db.commit()

        processed = run_once(db, worker_user_id=999)
        assert processed == "exp_test_1"

        refreshed = (
            db.query(models.ExportJob).filter(models.ExportJob.export_id == "exp_test_1").first()
        )
        assert refreshed is not None
        assert refreshed.status == "done"
        assert isinstance(refreshed.artifacts, list)
        assert refreshed.artifacts
        assert refreshed.artifacts[0]["inputs_hash"] == refreshed.inputs_hash

        actions = [row[0] for row in db.query(models.AuditLog.action).all()]
        assert "exports.job.started" in actions
        assert "exports.job.completed" in actions
        assert "exports.job.failed" not in actions


def test_exports_worker_transitions_to_failed_on_generator_error():
    SessionLocal = _make_db()

    def _boom(_job: models.ExportJob):
        raise RuntimeError("boom")

    with SessionLocal() as db:
        job = models.ExportJob(
            export_id="exp_test_2",
            inputs_hash="1" * 64,
            export_type="state",
            as_of=None,
            filters=None,
            status="queued",
            requested_by_user_id=1,
        )
        db.add(job)
        db.commit()

        processed = run_once(db, worker_user_id=999, artifacts_generator=_boom)
        assert processed == "exp_test_2"

        refreshed = (
            db.query(models.ExportJob).filter(models.ExportJob.export_id == "exp_test_2").first()
        )
        assert refreshed is not None
        assert refreshed.status == "failed"
        assert refreshed.artifacts is None

        actions = [row[0] for row in db.query(models.AuditLog.action).all()]
        assert "exports.job.started" in actions
        assert "exports.job.failed" in actions


def test_exports_worker_is_noop_when_no_queued_jobs():
    SessionLocal = _make_db()

    with SessionLocal() as db:
        processed = run_once(db, worker_user_id=999)
        assert processed is None
