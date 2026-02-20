# AGENTS.md

This file provides guidance to AI coding agents working with code in this repository.

## Overview

A CLI tool for interacting with Telegram.

## Architecture

*To be updated as the project structure takes shape.*

## Key Conventions

- Use uv for dependency management and virtual environments
- pyproject.toml is the single source for project metadata and dependencies
- Use pytest for testing
- Target Python >= 3.12

## When Editing

- Run `uv run pytest` to verify changes
- Keep CLI entrypoints thin; push logic into library modules
