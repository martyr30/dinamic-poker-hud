from pokerkit.notation import HandHistory, PokerStarsParser, parse_value
from pokerkit.utilities import Card
from re import compile, MULTILINE, search, Pattern, Match
from operator import add
from typing import Any, Callable, Generator, Set, Sequence
from collections import defaultdict

# 1. Создаем свой парсер, наследуясь от библиотечного
#    и переопределяя только то, что нам нужно.
class CustomPokerStarsParser(PokerStarsParser):
    """
    Наш собственный парсер, который расширяет логику поиска выигрыша.
    """
    # Паттерны для строк, которые нужно полностью игнорировать при парсинге действий
    IGNORED_ACTION_PATTERNS = (
        compile(r'.+ joins the table at seat #\d+'),
        compile(r'.+: sits out'),
    )
    # Паттерны для ставок и рейзов. Теперь это кортеж, а не одно выражение.
    COMPLETION_BETTING_OR_RAISING = (
        compile(r"(?P<player>.+): (bets|raises) \D?(?P<amount>[0-9.]+)"),
        compile(r'(?P<player>.+): raises \D?(?P<amount>[0-9.]+) to \D?[0-9.]+ and is all-in'),
    )
    PLAYER_VARIABLES = {
        'winnings': (
            (
                # 1. Выражение для строк со словом "collected"
                compile(r'(Seat \d+:)?'
                        r' (?P<player>.+)'
                        r' collected'
                        r' \(?\D?(?P<winnings>[0-9.,]+)\)?'
                        r'( from pot)?'),
                # 2. Новое выражение для строк со словом "won"
                compile(r'Seat \d+: '
                        r'(?P<player>.+?)'  # Нежадно захватываем имя игрока до...
                        # Пропускаем любой текст до нужной нам конструкции
                        r' (?:showed|won|\(small blind\)|\(big blind\)|\(button\)|mucked).* won \(\D?(?P<winnings>[0-9.,]+)\)'),
            ),
            None,  # parse_pattern (используется parse_value по умолчанию)
            int,   # default_value_factory
            add,   # merge function
        ),
    }

    # 1. Добавляем недостающий метод _format_cards
    def _format_cards(self, m: Match[str]) -> str:
        """Форматирует карты из совпадения регулярного выражения."""
        return ''.join(map(repr, Card.parse(m['cards'])))

    # 2. Добавляем недостающий метод _get_betting_action
    def _get_betting_action(
            self,
            bets: defaultdict[str, int],
            m: Match[str],
            parse_value: Callable[[str], int],
            line: str,
            format_player: Callable[[Match[str]], str],
    ) -> str:
        """
        Определяет действие ставки (колл, бет, рейз) на основе совпадения.
        """
        formatted_player = format_player(m)
        max_bet = max(bets.values(), default=0)

        # ВАЖНО: Вызываем оригинальный метод из PokerStarsParser для правильного расчета суммы.
        final_amount = super()._get_completion_betting_or_raising_to_amount(bets, formatted_player, parse_value(m['amount']), line)
        bets[formatted_player] = final_amount

        if final_amount <= max_bet:
            action = f'{formatted_player} cc'
        else:
            action = f'{formatted_player} cbr {bets[formatted_player]}'
        return action

    # Переопределяем метод, чтобы он мог работать с кортежем COMPLETION_BETTING_OR_RAISING
    def _parse_players(self, s: str) -> Set[str]:
        """
        Переопределенный метод для сбора имен игроков.
        Умеет работать с кортежем регулярных выражений для ставок/рейзов.
        """
        all_players_at_table = set()
        sitting_out_players = set()

        # За один проход находим всех игроков и тех, кто в ситауте
        for line in s.splitlines():
            # Ищем игроков по строкам 'Seat X: PlayerName (...)'
            if m := search(self.STARTING_STACKS, line):
                player_name = m.group('player')
                all_players_at_table.add(player_name)
                # Проверяем, не находится ли этот игрок в ситауте
                if 'is sitting out' in line:
                    sitting_out_players.add(player_name)

            # Дополнительная проверка для формата 'PlayerName: sits out'
            elif ': sits out' in line:
                player_name = line.split(':')[0].strip()
                sitting_out_players.add(player_name)

        # Возвращаем только активных игроков
        active_players = all_players_at_table - sitting_out_players
        return active_players

    # Переопределяем метод парсинга действий
    def _parse_actions(
            self,
            s: str,
            parse_value: Callable[[str], int],
            players: Sequence[str],
    ) -> list[str]:
        """
        Переопределенный метод для парсинга действий, который умеет
        работать с кортежем регулярных выражений для ставок и рейзов.
        """
        def format_player(m: Match[str]) -> str:
            player_index = players.index(m['player'])
            return f'p{player_index + 1}'

        bets = defaultdict(int)
        actions = []
        filtered_lines = [
            line for line in s.splitlines()
            if not any(pattern.match(line) for pattern in self.IGNORED_ACTION_PATTERNS)
        ]

        for i, line in enumerate(filtered_lines):
            action = None

            if m := search(self.BLIND_OR_STRADDLE_POSTING, line):
                bets[format_player(m)] = parse_value(m['blind_or_straddle'])
            elif m := search(self.HOLE_DEALING, line):
                action = f'd dh {format_player(m)} {self._format_cards(m)}'
            elif m := search(self.BOARD_DEALING, line):
                action = f'd db {self._format_cards(m)}'
                bets.clear()
            elif m := search(self.FOLDING, line):
                action = f'{format_player(m)} f'
            elif m := search(self.CHECKING_OR_CALLING, line):
                formatted_player = format_player(m)
                action = f'{formatted_player} cc'
                bets[formatted_player] = max(bets.values(), default=0)
            elif m := search(self.HOLE_CARDS_SHOWING, line):
                action = f'{format_player(m)} sm {self._format_cards(m)}'
            else:
                for pattern in self.COMPLETION_BETTING_OR_RAISING:
                    if m := search(pattern, line):
                        action = self._get_betting_action(bets, m, parse_value, line, format_player)
                        break

            if action is not None:
                actions.append(action)

        return actions

    # Этот метод нужен, чтобы PLAYER_VARIABLES мог обрабатывать кортеж из выражений
    def _parse_player_variables(
            self,
            s: str,
            parse_value: Callable[[str], Any],
    ) -> dict[str, defaultdict[str, Any]]:
        """
        Переопределенный метод для обработки выигрышей, который игнорирует
        игроков в ситауте.
        """
        # ВАЖНО: Сначала получаем список активных игроков, как это делает pokerkit
        # Мы вызываем оригинальный метод _parse_players из родительского класса.
        # Это гарантирует, что мы будем работать с тем же списком, что и остальная часть библиотеки.
        
        active_players = self._parse_players(s) # Используем наш переопределенный метод

        # Сначала найдем всех, кто в ситауте
        sitting_out_players = set()
        for line in s.splitlines():
            # ИСПРАВЛЕНО: Обрабатываем оба формата строк для "ситаута"
            if 'is sitting out' in line: # Формат: Seat X: PlayerName (...) is sitting out
                player_name = line.split(':')[1].split('(')[0].strip()
                sitting_out_players.add(player_name)
            elif ': sits out' in line: # Формат: PlayerName: sits out
                player_name = line.split(':')[0].strip()
                sitting_out_players.add(player_name)

        player_variables = {}

        for (
                key,
                (patterns, parse_pattern, default_value_factory, merge)
        ) in self.PLAYER_VARIABLES.items():
            sub_player_variables = defaultdict[str, Any](default_value_factory)

            if parse_pattern is None:
                parse_pattern = parse_value

            if not isinstance(patterns, (list, tuple, set)):
                patterns_to_check = (patterns,)
            else:
                patterns_to_check = patterns

            for line in s.splitlines():
                for pattern in patterns_to_check:
                    if m := search(pattern, line):
                        # ВАЖНО: Надежное извлечение имени игрока.
                        # Имя может быть как "Player (small blind)" так и просто "Player".
                        raw_player_name = m.group('player')
                        if '(' in raw_player_name:
                            player_in_line = raw_player_name.split('(')[0].strip()
                        else:
                            player_in_line = raw_player_name.strip()

                        # НОВАЯ ПРОВЕРКА: Убедимся, что найденный игрок есть в списке активных
                        if player_in_line not in active_players:
                            continue

                        if player_in_line in sitting_out_players:
                            continue

                        # ВАЖНО: Используем "чистое" имя игрока как ключ
                        sub_player_variables[player_in_line] = merge(
                            sub_player_variables[player_in_line],
                            parse_pattern(m[key]),
                        )
                        break  # Нашли совпадение, переходим к следующей строке

            if sub_player_variables:
                player_variables[key] = sub_player_variables

        return player_variables

# 2. Создаем свой класс истории раздач, наследуясь от HandHistory.
class CustomHandHistory(HandHistory):
    """
    Наш собственный класс HandHistory, который будет использовать
    наш кастомный парсер для PokerStars.
    """
    @classmethod
    def from_pokerstars(
            cls,
            s: str,
            *,
            parse_value: Callable[[str], int] = parse_value,
            error_status: bool = False,
    ) -> Generator['CustomHandHistory', None, int]:
        """
        Парсит историю раздач PokerStars, используя CustomPokerStarsParser.
        """
        # Здесь мы создаем экземпляр нашего парсера, а не стандартного.
        parser = CustomPokerStarsParser()
        
        # Вызываем его и возвращаем результат.
        # Тип возвращаемого значения будет генератором CustomHandHistory.
        yield from parser(
            s,
            parse_value=parse_value,
            error_status=error_status,
        )

# 3. Пример использования
if __name__ == '__main__':
    try:
        # content_string = '\n'.join(hand_history_input)

        with open('hands', 'r', encoding='utf-8') as f:
            content_string = f.read()

        # Используем проверенную рабочую функцию
        # hhs_iterator = HandHistory.from_pokerstars(content_string, error_status=True)
        hhs_iterator = CustomHandHistory.from_pokerstars(content_string, error_status=True)
        hhs_list = list(hhs_iterator)

        print(f"Обнаружено распарсенных раздач: {len(hhs_list)}")

        if not hhs_list:
            print("❌ ПАРСИНГ ПРОВАЛЕН. Парсер не смог распознать историю.")

        else:
            print("✅ ПАРСИНГ УСПЕШЕН.")
            hh = hhs_list[0]
            print(hh.seats)
            print(hh.players)
            print(hh.actions)
            print("---")

            print(hh.winnings)
            print("---")
            print(hh)
            print("---")
            # stats_to_commit = analyze_hand_for_stats(hh)
            # print(stats_to_commit)
            # update_stats_in_db(stats_to_commit)
            # print_player_statistics("Martyr40")

            # for state, action in hh.state_actions:
            #     if action:
            #         print(f"Карты: {state.hole_cards}, Выполненное действие: {action}")
            #         # print(f"Состояние: {state}, Выполненное действие: {action}")
            #     else:
            #         print(f"Начальное состояние: пока пропускаем")

    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")