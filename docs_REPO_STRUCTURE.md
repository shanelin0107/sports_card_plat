# Production-Minded Repo Structure

```text
sports_card_plat/
├── backend/
│   ├── app/
│   │   ├── api/v1/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   └── services/
│   ├── alembic/
│   ├── seed/
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/app/
│   ├── src/components/
│   ├── src/lib/
│   ├── package.json
│   └── Dockerfile
├── seed/
│   └── demo_seed.sql
├── scripts/
│   └── init_db.sql
├── docker-compose.yml
├── .env.example
└── README.md
```
