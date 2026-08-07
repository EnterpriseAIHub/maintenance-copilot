"""Shared pytest fixtures.

Kept intentionally empty of DB fixtures in Phase 1 — there are no models
to test against a real database yet. Phase 2 adds a `db_session` fixture
here (backed by the test Postgres instance the CI workflow already
provisions) once app/data/models exist.
"""
