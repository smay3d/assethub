# About the User

The user is a Pipeline TD in the VFX industry with beginner programming experience (about two years coding). He has used agentic coding before, but this is the first claude code extensive project and is still developing a workflow and understanding of certian processes. If the user seems unsure about something, research programming insustry practices and suggest a method to improve the user's workflow.

# Basic Description

**Purpose:** A singular hub to catalog, organize, and track a single user’s 3D art pipeline assets and metadata. Inspired by eagle asset manager, a similar tool specialized for designers.
**Target User:** Personal or small team leader
**Platform:** Windows

# Project Goal

This project, formerly known as AssetHub, is a singular hub to catalog, organize, and track a single user’s 3D art pipeline assets and metadata. The project is inspired by eagle asset manager, a similar tool specialized for designers that tracks file-on-disk image and other files. I found that as a 3D artist, this tool was insufficient for organizing my assets. Often, 3D art assets are made up of multiple files, for which eagle has no support. For example, a texture asset can be made up of one or more image files, each describing color, roughness, height, normal, metallic, or other properties for a 3D material. An image sequence can be any number of files in a specific order. A 3D model file will be regularly versioned up, saving previous versions in case a rollback is needed. AssetHub aims to resolve all these abstractions with a single browser, so an artist never has to ask themselves “Why is my material missing a texture map?” “Where did I put that render sequence?” or “What version of my model is being used in production?”

This project, originally built with an early ChatGPT code assistant workflow, is being rebooted with the first goal being an open beta release for real user feedback. First, we’ll audit the current prototype to determine what should be saved for the beta version and shape the core feature scope. Then, we’ll either update the prototype or start from scratch to build a production version of the asset organizer app for open beta testers. Real users will eventually use this product if enough positive feedback is received.

# Functionality Milestones

| Version | Core app functionality |
| --- | --- |
| MVP |   • File ingest and on-disk tracking (moved, renamed, deleted…)
  • Manual file → asset assignment
  • File / Asset search, filter, and sort (Notion-like table)
  • File duplicate detection |
| beta |   • Automatic asset detection
  • Asset version tracking |
| v1 release |   • Automatic project detection
  • Smart folders |
| future |   • Asset export to DCCs
  • AI powered file recognition?
  • Project law and auto linting |
| not in scope |  |


# CLAUDE.md file

We will design and create an efficent CLAUDE.md file based on the following outline as a starting point, keeping each item high level and citing the location of the documentation in the repo with further details. The CLAUDE.md file must remain consise but informative. Each section will link to a markdown file exposing details about the section's information and tell claude to reference it in case a process requires further information about a topic (See the Automated Documentation section).

## Outline:
**1. Project Goals:** Big-picture grounding of the project and folder layout
**2. Architecture Overview:** Big-picture grounding of the repo folder layout
**3. Design Style Guide:** Overview of tech stack, component patterns
**4. Product & UX Guidelines:** Core UX design principles and copy tone
**5. Constraints and Policies:**  Critical security procedures, code quality control, dependencies scope
**6. Reposity Etiquitte:** PRs v.s direct merges, commit policy, and git workflows
**7. Commands**: Frequently used commands for running the app and the testing suite

The CLAUDE.md file will be iterated upon as the project continues.

# Automated Documentation

Core Docs:
1. **Raptor_Architecture.md**: Documents system design, app structure, and how major components interact. Always update after big features are completed.
2. **Raptor_Changelog.md**: List of all notable changes over time. Gives Claude an overview of how the project has evolved over time.
3. **Raptor_Status.md**: Tracks project milestones, accomplishments in relation to the milestones, where did the last session leave off.

We will implement the automatic documentation update via either an instruction in the CLAUDE.md file custom skill. I prefer creating a skill, we'll use Anthropic's /skill-creator skill for this. Here's an outline for the skill:

## Auto Doc Skill
**Usage:**
/update-docs-and-commit [optional commit message or description]

**What it does:**
1. Analyzes git changes (status + diff)
2. Updates docs/Raptor_Changelog.md - adds entries for new features/fixes
3. Updates docs/Raptor_Architecture.md - only if structural changes occured
4. Updates docs/Raptor_Status.md - moves completed items, updates progress
5. Stages and commits all changes

The command is conservative by design - it only updates docs that genuinely need updating based on the actual code changes.

# Plugins

**Anthropic**
- skill-creator
- superpowers
- frontend-design
- feature-dev
- compound-engineering

# MCP servers

I'm not entirely sure what this is, but I'm told they're useful based on the tech stack. For example, perhaps we set up a mcp for the db.

# Custom /commands and subagents

A slash command is a shortcut to a proompt or task, using the same context window as the prompt. A subagent is a specialized agent for a specific task, using a fork of the main context window. Subagents do not know about eachother.

Retro agent: Reflects on what can be improved after a development session and updates things like CLAUDE.mdand slash commands with its findings. I'd like to implement one of these, but my source did not list one to try. 