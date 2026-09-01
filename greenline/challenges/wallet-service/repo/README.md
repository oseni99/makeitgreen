# wallet-service

Peer-to-peer wallet transfers with a 1% transfer fee (minimum 1 cent).
All amounts are integer cents — no floats, ever.

- `wallet_service/service.py` — balances, deposits, transfers
- `wallet_service/errors.py` — domain exceptions

Run tests: `python -m pytest -v`
