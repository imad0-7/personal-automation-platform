"""Single authorized subscriber today; preferences are scoped for future subscribers."""
from __future__ import annotations

import html
import shlex

from automation_platform.core.models import Notification

DEFAULTS = {'mode': 'resume', 'reports': True}
HELP = ('/mode tous | offres | resume | pause\n/rapport on | off\n/test\n/status\n'
        '/corriger ID ram_gb=32 ram_type=DDR5\n'
        'Commandes traitées au prochain lancement (environ 15 minutes).')


def poll_commands(repo, notifier, namespace: str) -> None:
    if not hasattr(notifier, 'get_updates'):
        return
    offset = repo.state(namespace, 'telegram_offset', 0)
    for update in notifier.get_updates(offset):
        uid = update['update_id']
        msg = update.get('message', {})
        chat = msg.get('chat', {})
        if str(chat.get('id')) != notifier.chat_id or chat.get('type') != 'private':
            repo.set_state(namespace, 'telegram_offset', uid + 1)
            continue
        prefs = repo.state(namespace, 'preferences', DEFAULTS.copy())
        text = msg.get('text', '').strip()
        answer = HELP
        if text.startswith('/mode '):
            mode = text.split(maxsplit=1)[1].lower()
            if mode in {'tous', 'offres', 'resume', 'pause'}:
                prefs['mode'] = mode
                answer = f'Mode : {mode}'
        elif text in {'/rapport on', '/rapport off'}:
            prefs['reports'] = text.endswith(' on')
            answer = 'Compte rendu à chaque scan : ' + ('oui' if prefs['reports'] else 'non')
        elif text == '/test':
            answer = 'TEST : Alfred fonctionne. Ceci est un test, pas une nouvelle annonce.'
        elif text == '/status':
            answer = f"Mode : {prefs['mode']} — rapports : {prefs['reports']}\n"
            answer += str(repo.state('cashconverters-v2', 'last_status', 'Pas encore de scan V2'))
        elif text.startswith('/corriger '):
            try:
                args = shlex.split(text)
                ident = args[1]
                if repo.get_listing('cashconverters', ident) is None:
                    raise ValueError('Annonce inconnue')
                values = {}
                for arg in args[2:]:
                    key, value = arg.split('=', 1)
                    if key not in {'cpu', 'platform', 'gpu', 'ram_gb', 'ram_type'}:
                        raise ValueError('Champ non autorisé')
                    if key == 'ram_gb':
                        value = int(value)
                        if not 1 <= value <= 1024:
                            raise ValueError('Quantité de RAM invalide')
                    if key == 'platform' and value not in {'AM4', 'AM5', 'inconnu'}:
                        raise ValueError('Plateforme invalide')
                    if key == 'ram_type' and value not in {'DDR3', 'DDR4', 'DDR5', 'inconnu'}:
                        raise ValueError('Type de RAM invalide')
                    values[key] = value
                if not values:
                    raise ValueError('Aucune correction')
                current = repo.state(namespace, 'correction:' + ident, {})
                current.update(values)
                repo.set_state(namespace, 'correction:' + ident, current)
                queue = repo.state(namespace, 'review', {})
                queue.pop(ident, None)
                repo.set_state(namespace, 'review', queue)
                answer = 'Correction enregistrée pour cette annonce uniquement.'
            except (ValueError, IndexError):
                answer = 'Correction invalide. Exemple : /corriger 12345 ram_gb=32 ram_type=DDR5'
        repo.set_state(namespace, 'preferences', prefs)
        repo.queue_event('cashconverters', f'{namespace}:command:{uid}',
                         Notification(title='ALFRED', message=html.escape(answer)))
        repo.set_state(namespace, 'telegram_offset', uid + 1)
