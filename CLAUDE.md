# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

This project provides a simple, easy-to-set-up interface around [WhisperX](https://github.com/m-bain/whisperX) for automatic audio transcription, aimed at **non-technical users** on both **Windows and macOS**.

## Current State

The repository is empty — no code, build system, or tooling exists yet. This section should be replaced with real build/run/test commands and architecture notes as the project takes shape.

## Design Constraints

- **Audience is non-technical**: setup and everyday use must not require the command line, Python knowledge, or manual dependency management. Installation should be as close to one-click as possible.
- **Cross-platform**: everything must work on both Windows and macOS. Avoid platform-specific solutions unless a per-platform equivalent is provided.
- **WhisperX is the transcription engine**: WhisperX is a Python package with heavy dependencies (PyTorch, ffmpeg, CUDA on Windows/NVIDIA vs. CPU/MPS on macOS). Any packaging or environment-bootstrapping approach must handle these per-platform differences without user intervention.
