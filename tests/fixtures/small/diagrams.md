# Diagrams

Intro.

```mermaid
---
title: Order flow
---
flowchart LR
    A --> B
    B --> C
```

```python
# a code block, not a diagram
print("hi")
```

## Other languages

~~~ dot
strict digraph G {
  a -> b
}
~~~

```plantuml
@startuml
title Login
Alice -> Bob: hello
@enduml
```

```d2
x -> y
```

```puml
@startmindmap
* root
@endmindmap
```

## Not diagrams

> ```mermaid
> graph TD
> ```

- ```mermaid
  pie
  ```

```mermaid
%% a comment first
sequenceDiagram
    title Checkout
    A->>B: pay
