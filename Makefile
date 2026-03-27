.PHONY: all up down seed bench report clean

all: up seed bench report

up:
	docker compose up -d --wait

down:
	docker compose down -v

seed:
	uv run python benchmark/data/seed.py

setup-cognimesh:
	uv run python benchmark/cognimesh_app/setup.py

bench: setup-cognimesh
	uv run pytest benchmark/tests/ -q --tb=short --no-header \
		--benchmark-json=benchmark/results/benchmark.json

report:
	uv run python benchmark/harness/report.py

clean:
	docker compose down -v
	rm -rf benchmark/results/
