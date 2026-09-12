from automation_platform.core.database.sqlite import SQLiteRepository
from automations.cashconverters.controls import poll_commands


class Commands:
    chat_id = '42'

    def get_updates(self, offset):
        return [
            {'update_id': 10, 'message': {'chat': {'id': 99, 'type': 'private'}, 'text': '/mode pause'}},
            {'update_id': 11, 'message': {'chat': {'id': 42, 'type': 'private'}, 'text': '/mode offres'}},
            {'update_id': 12, 'message': {'chat': {'id': 42, 'type': 'private'}, 'text': '/test'}},
        ]


def test_commands_are_scoped_to_authorized_chat(tmp_path):
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    poll_commands(repo, Commands(), 'subscriber:42:cashconverters')
    assert repo.state('subscriber:42:cashconverters', 'preferences')['mode'] == 'offres'
    assert repo.state('subscriber:42:cashconverters', 'telegram_offset') == 13
    assert len(repo.pending_notifications('cashconverters')) == 2
