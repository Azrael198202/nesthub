# codex-feeding-order.md

Updated: 2026-04-23

## Purpose

This document defines the **correct feeding order and execution strategy for Codex** when implementing the core-brain system.

DO NOT provide all documents at once.

Codex must follow staged execution.

---

## 1. Overall Strategy

Implementation must be split into **two phases**:

### Phase 1 — Foundation

Build system structure, contracts, and execution skeleton.

### Phase 2 — Advanced Capability

Build dynamic generation:

- agent_creation_intent
- blueprint generation
- tool_builder

---

## 2. Feeding Order (Strict)

### Step 1 — System Definition

Provide:

- core-brain-implementation-v2.md

#### Goal

Define:

- architecture
- layers
- model routing
- core concepts

#### Expected Output

- core_brain unified structure
- main entrypoint
- layer separation

---

### Step 2 — JSON Rules + Schema

Provide:

- core-brain-json-rules.md
- intent.schema.json
- workflow.schema.json
- blueprint.schema.json
- tool.schema.json
- trace.schema.json

### Step 2 ： Goal

Lock ALL data structures.

### Critical Rules

- No free-form dict allowed
- All runtime objects must match schema
- Validation must be implemented

### Step 2 ： Expected Output

- contracts/ directory
- schema validation layer
- DTO alignment

---

### Step 3 — Execution Checklist

Provide:

- core-brain-codex-execution-checklist.md

#### Step 3： Goal

Guide actual refactoring.

### Step 3： Expected Output

- core → core_brain merge
- models vs brain separation
- workflows modularization
- kb minimal implementation
- generated lifecycle structure
- trace + validation framework

---

### Phase 1 Completion Criteria

System must support:

- intent parsing
- workflow planning
- step execution
- trace generation
- validation
- artifact lifecycle

WITHOUT:

- dynamic agent creation
- tool generation

---

## 4. Phase 2 — Advanced Features

### Step 4 — Agent Creation + Tool Builder

Provide:

- core-brain-agent-creation-and-tool-builder.md

### Step 4： Goal

Enable:

- agent_creation_intent
- blueprint auto-generation
- workflow auto-generation
- tool resolution
- tool_builder
- runtime agent instantiation

---

## 5. Execution Rules (MANDATORY)

Codex MUST follow:

1. Do NOT skip schema enforcement
2. Do NOT implement tool_builder before contracts
3. Do NOT mix refactor + new feature in one step
4. Do NOT generate tools without contract first
5. Do NOT register artifacts without validation
6. Do NOT treat logs as trace
7. Do NOT assume tools already exist
8. Do NOT bypass workflow for agent creation
9. Do NOT activate agent before registration
10. Do NOT ignore lifecycle states

---

## 6. Anti-Patterns (MUST AVOID)

### ❌ Wrong Order

- Build tool_builder first
- Then try to define schema

### ❌ Mixed Responsibilities

- brain layer doing tool execution
- model layer doing prompt logic

### ❌ Weak Structure

- dynamic dict instead of schema
- missing validation

### ❌ Missing Trace

- print logs instead of structured trace

---

## 7. Final Execution Timeline

### Phase 1 (Foundation)

1. implementation-v2
2. json rules + schema
3. execution checklist

### Phase 2 (Advanced)

4. agent creation + tool builder

---

## 8. Final Summary

Correct execution order:

implementation
→ schema
→ refactor
→ advanced features

DO NOT reorder.

DO NOT merge phases.

DO NOT skip validation.

System correctness depends on execution discipline.
