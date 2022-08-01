clock: python -OO -m polarity.delete_commands && python -OO -m polarity.main & python -OO -m polarity.reset_signaller
release: cd polarity && alembic upgrade head && cd .. && python -OO -m polarity.release
delete_commands: python -m polarity.delete_commands