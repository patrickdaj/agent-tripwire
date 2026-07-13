## ADDED Requirements

### Requirement: Run output visually delimits each action

The run output SHALL give each classified action a clear visual boundary so that adjacent
entries are distinguishable and do not run together, in both the rich and plain renderers.

#### Scenario: Rich rows are ruled off

- **WHEN** the run renders more than one action with `rich` enabled
- **THEN** each action's row is separated from the next by a horizontal divider

#### Scenario: Plain blocks are numbered and separated

- **WHEN** the run renders the actions in plain text
- **THEN** each action is numbered and separated from the next by a separator line, so where one action ends and the next begins is unambiguous

### Requirement: A misclassification is rendered prominently

The run output SHALL surface a miss — a classification that disagrees with its input's
expected label — with a leading, high-contrast status indicator rather than only a trailing
marker, and SHALL keep it identifiable when color is unavailable. This is a presentation
requirement only: a miss remains non-gating and never changes the exit code.

#### Scenario: A miss leads with a status indicator

- **WHEN** an action's verdict does not match its expected label
- **THEN** the entry is marked at its leading edge with a distinct status (e.g. a `MISS` label), not only a trailing symbol

#### Scenario: A miss is identifiable without color

- **WHEN** the output is rendered in plain text (color unavailable — `NO_COLOR`, a non-TTY, or `rich` absent)
- **THEN** the miss is still identifiable by a textual status word, not by color alone

#### Scenario: An error is distinct from a miss

- **WHEN** an action fails to produce a valid classification (an error) and another action is merely a miss
- **THEN** the two are shown with distinct status labels

#### Scenario: Prominence does not change the exit contract

- **WHEN** the run contains a prominently-marked miss but every action produced a valid classification
- **THEN** the process still exits successfully
