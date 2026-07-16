update:
	git pull && docker compose up -d --build

# Faqat bitta xizmatni yangilash kerak bo'lsa:
update-bot:
	git pull && docker compose up -d --build bot

update-admin:
	git pull && docker compose up -d --build adminka

logs:
	docker compose logs -f bot

logs-admin:
	docker compose logs -f adminka

ps:
	docker compose ps

restart:
	docker compose restart
