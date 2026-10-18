# AETHER — convenience commands
.PHONY: help dev build preview install update docker-up docker-down docker-logs clean

help:           ## Show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*##"}{printf "  %-14s %s\n", $$1, $$2}'

dev:            ## Local dev server (hot reload) on :5173
	npm run dev

build:          ## Production build → dist/
	npm run build

preview: build  ## Build then preview the production bundle
	npm run preview

install:        ## Full Linux-server install (Nginx). Args: DOMAIN=x SSL=mail
	sudo bash install.sh $(if $(DOMAIN),--domain $(DOMAIN)) $(if $(SSL),--ssl $(SSL))

update:         ## Redeploy latest code on the server
	sudo bash update.sh

docker-up:      ## Deploy with Docker Compose (PORT=8080 default)
	PORT=$(or $(PORT),8080) docker compose up -d --build

docker-down:    ## Stop the Docker deployment
	docker compose down

docker-logs:    ## Follow container logs
	docker compose logs -f

clean:          ## Remove build output & deps
	rm -rf dist node_modules
