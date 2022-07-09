clock: python -OO -m polarity.main & python -OO -m polarity.reset_signaller
release: cd polarity && alembic upgrade head && cd .. && python -m polarity.release
delete_commands: python -m polarity.delete_commands