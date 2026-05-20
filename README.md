# AirShero – Data Generator

Python-based synthetic data generator for the AirShero airline database.
Generates realistic test data for all 56 tables across three generation layers.

## Tech Stack

- **Python** – core language
- **SQLAlchemy** – database connection and ORM
- **Faker** – synthetic data generation
- **MS SQL Server** – target database
- **JSON** – static reference data source

## How It Works

Data generation is organized into three layers executed sequentially:

1. **Classification** – reference and lookup tables (statuses, types, categories)
2. **Objects** – core entities (passengers, flights, routes, crew, airports)
3. **Documentary** – transactional data (bookings, payments, check-ins, boarding passes)

Some reference tables are populated from JSON files stored in `files/`.

## Related Repositories

- [AirShero Backend](https://github.com/roksolana-shendiukh/airshero-backend)
- [AirShero Frontend](https://github.com/roksolana-shendiukh/airshero-frontend)
- [AirShero Database](https://github.com/roksolana-shendiukh/airshero-db)
