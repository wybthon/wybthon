"""Tic-tac-toe — a complete game in pure Python, in the browser.

Tweet caption:
    Tic-tac-toe in 50 lines of Python. Reactive board, win detection,
    reset — and it runs in the browser. No JavaScript, no JSX.

Why it's interesting:
    The board is a single signal (a tuple of 9 cells). `winner` and
    `status` are memos derived from it — they recompute automatically
    on every move. Only the changed cell's text updates in the DOM.
"""

from wybthon import button, component, create_memo, create_signal, div, dynamic, p

LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def _winner(board):
    for a, b, c in LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return None


@component
def TicTacToe():
    board, set_board = create_signal((None,) * 9)
    turn, set_turn = create_signal("X")
    winner = create_memo(lambda: _winner(board()))
    status = create_memo(lambda: f"Winner: {winner()}" if winner() else f"Turn: {turn()}")

    def play(i):
        def handler(_e):
            if board()[i] or winner():
                return
            next_board = list(board())
            next_board[i] = turn()
            set_board(tuple(next_board))
            set_turn("O" if turn() == "X" else "X")

        return handler

    def reset(_e):
        set_board((None,) * 9)
        set_turn("X")

    def cell(i):
        return button(
            dynamic(lambda: board()[i] or " "),
            on_click=play(i),
            style={"width": "48px", "height": "48px", "fontSize": "24px"},
        )

    return div(
        p(dynamic(status)),
        div(*(cell(i) for i in range(9)), style={"display": "grid", "gridTemplateColumns": "repeat(3, 48px)"}),
        button("Reset", on_click=reset),
    )
