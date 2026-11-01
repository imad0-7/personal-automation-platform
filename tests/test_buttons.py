import json

import httpx

from automation_platform.core.database.sqlite import SQLiteRepository
from automation_platform.core.http import HttpClient
from automation_platform.core.models import Notification
from automation_platform.integrations.telegram import TelegramNotifier
from automations.cashconverters.buttons import attach_buttons, callback_command
from automations.cashconverters.controls import poll_commands
from automations.cashconverters.watch import WATCH_STATE

URL = 'https://www.cashconverters.be/fr/accessoires-informatique/123-gpu.html'
NS = 'subscriber:42:cashconverters'


def callback(uid, data, sender=42, chat_id=42, chat_type='private'):
    return {'update_id': uid, 'callback_query': {'id': f'query-{uid}',
            'from': {'id': sender}, 'data': data,
            'message': {'chat': {'id': chat_id, 'type': chat_type}}}}


class Bot:
    chat_id = '42'

    def __init__(self, updates):
        self.updates = updates
        self.answered = []

    def get_updates(self, offset):
        return [x for x in self.updates if x['update_id'] >= offset]

    def answer_callback(self, query_id):
        self.answered.append(query_id)


def test_product_buttons_and_telegram_payload(tmp_path):
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    notification = Notification('GPU', 'RTX 4090', url=URL)
    attach_buttons(repo, NS, notification)
    captured = {}

    def handler(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={'ok': True})

    with HttpClient(transport=httpx.MockTransport(handler)) as client:
        TelegramNotifier('fake-token', '42', client).notify(notification)
    rows = captured['reply_markup']['inline_keyboard']
    assert rows[0][0]['url'] == URL
    data = [button['callback_data'] for row in rows for button in row if 'callback_data' in button]
    assert {'cc:price:123', 'cc:burst:123', 'cc:stop:123', 'cc:list:all', 'cc:help'} <= set(data)
    assert all(len(x.encode()) <= 64 for x in data)
    assert repo.state(NS, 'button_product:123') == URL
    repo.close()


def test_callbacks_add_price_upgrade_burst_stop_and_replay(tmp_path):
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    attach_buttons(repo, NS, Notification('GPU', 'card', url=URL))
    bot = Bot([callback(1, 'cc:price:123')])
    poll_commands(repo, bot, NS)
    assert repo.state(NS, 'watches')['123']['price']
    assert not repo.state(NS, 'watches')['123']['reservation']
    bot.updates.append(callback(2, 'cc:burst:123'))
    poll_commands(repo, bot, NS)
    assert repo.state(NS, 'watches')['123']['burst']
    bot.updates.append(callback(3, 'cc:stop:123'))
    poll_commands(repo, bot, NS)
    assert not repo.state(NS, 'watches')
    assert bot.answered == ['query-1', 'query-2', 'query-3']
    sent_count = len(repo.pending_notifications('cashconverters'))
    poll_commands(repo, bot, NS)
    assert len(repo.pending_notifications('cashconverters')) == sent_count
    repo.close()


def test_callbacks_require_authorized_sender_private_chat_and_registered_url(tmp_path):
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    attach_buttons(repo, NS, Notification('GPU', 'card', url=URL))
    bot = Bot([callback(1, 'cc:price:123', sender=99),
               callback(2, 'cc:price:123', chat_id=99),
               callback(3, 'cc:price:123', chat_type='group'),
               callback(4, 'cc:price:999'), callback(5, 'cc:price:https://evil.test')])
    poll_commands(repo, bot, NS)
    assert not repo.state(NS, 'watches', {})
    assert len(bot.answered) == 2
    assert len(repo.pending_notifications('cashconverters')) == 2
    repo.set_state(WATCH_STATE, URL, {'removed': True})
    command, error = callback_command(repo, NS, 'cc:burst:123')
    assert command is None and 'disparu' in error
    repo.close()


def test_menu_text_inline_menu_and_list_stop_buttons(tmp_path):
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    bot = Bot([{'update_id': 1, 'message': {'chat': {'id': 42, 'type': 'private'},
                                         'text': '❓ Aide'}}])
    poll_commands(repo, bot, NS)
    reply = repo.pending_notifications('cashconverters')[0][1]
    assert 'AIDE ALFRED' in reply.message
    attach_buttons(repo, NS, reply)
    assert reply.metadata['reply_markup']['inline_keyboard']
    repo.set_state(NS, 'watches', {'123': {'url': URL, 'title': 'GPU'}})
    bot.updates.append(callback(2, 'cc:list:all'))
    poll_commands(repo, bot, NS)
    reply = repo.pending_notifications('cashconverters')[-1][1]
    attach_buttons(repo, NS, reply)
    rows = reply.metadata['reply_markup']['inline_keyboard']
    assert any(b.get('callback_data') == 'cc:stop:123' for row in rows for b in row)
    report = Notification('Report', 'No new items')
    attach_buttons(repo, NS, report)
    assert report.metadata['reply_markup']['is_persistent']
    final = Notification('Gone', 'No longer exists', url=URL, metadata={'watch_final': True})
    attach_buttons(repo, NS, final)
    assert 'inline_keyboard' not in final.metadata['reply_markup']
    repo.close()


def test_telegram_polls_callbacks_and_expired_ack_does_not_block_processing(tmp_path):
    repo = SQLiteRepository(tmp_path / 'state.db')
    repo.migrate()
    attach_buttons(repo, NS, Notification('GPU', 'card', url=URL))
    calls = []

    def handler(request):
        calls.append((request.url.path.rsplit('/', 1)[-1], json.loads(request.content)))
        if request.url.path.endswith('/getUpdates'):
            return httpx.Response(200, json={'ok': True, 'result': [callback(1, 'cc:price:123')]})
        return httpx.Response(400, json={'ok': False, 'description': 'Query is too old'})

    with HttpClient(transport=httpx.MockTransport(handler)) as client:
        poll_commands(repo, TelegramNotifier('fake-token', '42', client), NS)
    assert calls[0][1]['allowed_updates'] == ['message', 'callback_query']
    assert calls[1][0] == 'answerCallbackQuery'
    assert repo.state(NS, 'watches')['123']['price']
    assert repo.state(NS, 'telegram_offset') == 2
    repo.close()
