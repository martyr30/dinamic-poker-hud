from my_pokerkit_parser import CustomHandHistory
from poker_globals import MY_PLAYER_NAME

with open('manual_hand.txt', 'r') as f:
    content = f.read()

hh = list(CustomHandHistory.from_pokerstars(content))[0]

print(f"HH Attributes: {dir(hh)}")
if hasattr(hh, 'actions'):
    # Iterate actions? hh is not a game, it's a HandHistory definition.
    # It has a method create_game() which returns a Game object.
    # The actions are arguments to create_game?
    # hh.actions attribute usually exists.
    print("Actions Attribute Found.")
    for i, action in enumerate(hh.actions):
        print(f"Action {i}: {action} Type: {type(action)}")
        if hasattr(action, 'cards'):
            print(f"  -> Cards: {action.cards}")
else:
    print("No actions attribute.")
    # Maybe iterate hh (which yields states)?
    # hh itself has 'preflop_actions', 'flop_actions' etc lists?
    print(f"Preflop Actions: {len(hh.preflop_actions) if hasattr(hh, 'preflop_actions') else 'None'}")
