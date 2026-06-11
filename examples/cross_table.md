# Cross-table references

Two tables in the same file can reference each other by name.

| <!-- table:rates --> Label  | Value |
| :---                      | ----: |
| Base rate                 | 500   |

| <!-- table:calc --> Metric | Result                    |
| :---                     | ------------------------: |
| Adjusted (10 %)          | <!-- =rates!B1 * 0.10 --> |
