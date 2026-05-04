# Java Docs Lens

## Overview

Java Docs Lens is a local study web app for exploring the latest Oracle Java documentation through English terms, Chinese concepts, and symbol-based queries. It helps learners move from a natural question, such as "Can this idea be expressed in Java?" to the most relevant official Oracle documentation page, then supports learning with Chinese explanation, official concept summary, interview-style review, and runnable code snippets.

This project addresses a common learning problem: many students do not start with the exact API name, but with an idea, a concept in their native language, or a syntax fragment such as `%-`, `::`, or `->`. The project demonstrates how to combine official documentation lookup, multilingual query expansion, and a lightweight learning interface into a practical local tool.

## Motivation

This project was built to support concept-driven Java learning, especially for students whose native language is not English and who want to explore beyond textbook explanations. Instead of stopping at brief descriptions, the goal is to help learners quickly reach official Oracle content and understand how a Java concept is used in practice.

The project also reflects a personal learning journey: entering Java from a different professional background, with the intention of using Java to express real ideas, workflows, and experiences from another field. From a technical perspective, the project was motivated by the challenge of connecting multilingual search, official documentation extraction, and interactive runnable examples in a simple local application.

## Features

- Search the latest Oracle Java documentation with English, Chinese, and symbol-based input
- Extract official Oracle excerpts and signatures for matched Java concepts
- Present Chinese explanation and official concept summary in the Knowledge Summary tab
- Provide runnable Java code snippets with embedded notes, guided input, and verified output

## Technologies Used

- Programming language: Python, JavaScript, HTML, CSS, Java
- Frameworks or libraries: Python standard library (`http.server`, `urllib`, `threading`, `ssl`, `re`, `json`)
- Tools: VS Code, local browser, `javac`, `java`, command-line smoke tests
- Database, if applicable: None
- Version control: GitHub-ready project structure, though the current local folder is not initialized as a Git repository

## Project Structure

```text
Java_Study/
│
├── README.md
├── DESIGN_DOC.md
├── server.py
├── smoke_test.py
├── static/
│   ├── index.html
│   ├── app.js
│   ├── styles.css
│   └── hero-portrait.svg
└── __pycache__/
```
