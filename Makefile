##
# Project Title
#
# @file
# @version 0.1

help: ## Show this help
	@printf '\nUsage:\n  make \033[36m<target>\033[0m\n\nTargets:\n' && egrep '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf"  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
# all: build create start setup stop


enter: ## enter kernel build container
	@docker-compose -f build_kernel/docker-compose.yaml exec sl101-kernel-builder bash

build: ## rebuild kernel build container
	@docker-compose -f build_kernel/docker-compose.yaml build
	#
kernel: ## build kernel in docker container
	# @docker-compose -f docker/docker-compose.yaml build
	@docker-compose -f build_kernel/docker-compose.yaml up -d
	# @docker-compose -f docker/docker-compose-dev.yaml exec sr_flashtool /usr/sbin/start

stop: ## stop kernel container
	@docker-compose -f build_kernel/docker-compose.yaml down
