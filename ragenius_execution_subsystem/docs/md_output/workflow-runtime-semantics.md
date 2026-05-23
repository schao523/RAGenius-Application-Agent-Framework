Workflow Runtime Semantics
The workflow defines the internal sequence of actions that a skill performs to transform its input into a
result. In the RAGenius Execution Subsystem, workflows are declarative and interpreted by the workflow
orchestrator at runtime. This document describes the semantics of workflow steps, execution flow, error
handling, retries and compensation.
Step Types
Each workflow is composed of a list of steps. Each step has a unique id and a type that determines how
it is executed.
Type Description Typical usage
Performs a local check on the
execution context or input. It does
Check field length, verify
validation not call external services. On
preconditions
failure, the workflow stops with a
validation error.
Invokes a registered tool through
the tool engine. The step must
Call rag_retrieval_tool ,
tool_call specify tool_id and may
mock_video_generation_tool
include input and output
mappings.
Evaluates a boolean condition to
decide which branch to follow. The
local_decision Dry run check
condition can reference context
values.
Executes a nested workflow,
allowing reuse of sub?flows or
internal_workflow Subroutine for generating a report
composition of common
sequences.
Calls an internal service (e.g. skill
registry, permission engine). Load skill metadata, check
service_call
Generally used for system?level permissions
operations.
Defines a compensation sequence
Roll back file creation, delete external
saga that runs if a preceding step fails
documents
after side effects.
1

| Type | Description |     |     | Typical usage |     |
| ---- | ----------- | --- | --- | ------------- | --- |
Terminates the workflow. It may
end specify a status (e.g.  success ,  End states for success or failure
|     | fail_validation |     | ).  |     |     |
| --- | --------------- | --- | --- | --- | --- |
Step Structure
steps:
- id: <string>
| type: <string>             |           |           |                        |     |     |
| -------------------------- | --------- | --------- | ---------------------- | --- | --- |
| action: <string or object> |           |           |                        |     |     |
| input_mapping:             | <mapping> |           | # optional             |     |     |
| output_mapping:            | <mapping> |           | # optional             |     |     |
| retry:                     |           |           | # optional             |     |     |
| max: <integer>             |           |           |                        |     |     |
| backoff_ms:                | <integer> |           |                        |     |     |
| on:                        |           |           | # optional transitions |     |     |
| success:                   | <step_id> |           |                        |     |     |
| failure:                   | <step_id> |           |                        |     |     |
| partial:                   | <step_id> |           |                        |     |     |
| requires_confirmation:     |           | <step_id> |                        |     |     |
Fields
ò  id : Unique identifier within the workflow. Use descriptive names such as  validate_prompt  or
| generate_video                        | .         |              |     |     |     |
| ------------------------------------- | --------- | ------------ | --- | --- | --- |
| ò  type : Step type as defined above. |           |              |     |     |     |
| action                                | tool_call | service_call |     |     |     |
ò  : For   and  , this references the tool ID or binding reference.
For  validation , it can be the name of a local validation function. For  internal_workflow , it
references a sub?workflow definition.
ò  input_mapping : Maps values from the execution context to the tool or service input. Use
JMESPath or JSON?pointer syntax to reference fields (e.g.  $.input.prompt  or
| $.steps.retrieve_context.output.context |     |     |     | ).  |     |
| --------------------------------------- | --- | --- | --- | --- | --- |
ò  output_mapping : Maps values from the tool or service output back into the execution context.
| Keys become available under  |     | $.steps.<step_id>.output |     | .   |     |
| ---------------------------- | --- | ------------------------ | --- | --- | --- |
ò  retry : Optional retry policy.  max  is the number of retries and  backoff_ms  is the delay
|                                          |     |     | tool_call | service_call |         |
| ---------------------------------------- | --- | --- | --------- | ------------ | ------- |
| between attempts. Retries apply only to  |     |     |           |  and         |  types. |
ò  on : Defines transitions based on outcome.  success ,  failure ,  partial , or
requires_confirmation  point to the next step ID. If omitted, the workflow ends.
Input and Output Mapping
Use mapping expressions to bind data between steps. The left?hand side is the expected parameter name
for the tool or service; the right?hand side is a JSON path expression pointing into the current execution
context. For example:
2

input_mapping:
| prompt: $.input.prompt                           |     |     |     |     |
| ------------------------------------------------ | --- | --- | --- | --- |
| duration: $.input.duration                       |     |     |     |     |
| context: $.steps.retrieve_context.output.context |     |     |     |     |
output_mapping:
| video_title:              | $.output.title   |     |     |     |
| ------------------------- | ---------------- | --- | --- | --- |
| video_summary:            | $.output.summary |     |     |     |
| file_id: $.output.file_id |                  |     |     |     |
Execution Semantics
1. Sequential execution: Steps execute in the order they are defined unless transitions specify jumps.
Each step starts only after the previous one finishes.
2. Context accumulation: The execution context accumulates intermediate outputs. Each stepÆs
output is stored under  $.steps.<step_id>.output  and can be referenced by subsequent steps.
3. Branching: local_decision  steps evaluate a boolean and choose the next step. The  on  block
for a step can define different targets based on outcome classes (success, failure, partial,
requires_confirmation).
4. Failure propagation: If a step fails and has no explicit  on.failure  transition, the workflow stops
and the execution is marked as  failed . Partial failures may set status  partial  if some data is
recoverable.
retry
5. Retry logic: If   is defined, the workflow orchestrator will retry the step upon a classified
tool  or  external_api  error until the  max  count is reached. Validation and permission errors
are not retried.
6. Compensation: A  saga  step defines compensation actions. If a step with side effects succeeds and
a later step fails, the orchestrator will run the compensation steps in reverse order to roll back side
effects. Compensation steps themselves may have retries.
7. Confirmation: If a tool requires confirmation ( require_confirmation  permission mode), the
orchestrator pauses execution and returns a  pending_confirmation  result. Upon confirmation,
execution should resume from the specified step.
8. Timeouts: Step timeouts are enforced by the tool engine. A timeout is classified as  timeout  error
and may be retried if configured.
9. Completion: If the last executed step reaches an  end  node with status  success_completed , the
|     |     | completed | fail_* | failed |
| --- | --- | --------- | ------ | ------ |
execution result is marked  . If it reaches a   end, the result is   or
| partial  accordingly. |     |     |     |     |
| --------------------- | --- | --- | --- | --- |
Error Classes
Workflows classify errors according to the domain error model:
| Error Class | Meaning |     | Retryable |     |
| ----------- | ------- | --- | --------- | --- |
Input or context did not match
| validation |     |     | No  |     |
| ---------- | --- | --- | --- | --- |
expected schema.
3

| Error Class | Meaning                             | Retryable                |     |
| ----------- | ----------------------------------- | ------------------------ | --- |
|             | Permission policy did not allow the | Typically no; may allow  |     |
permission
|     | operation. | require_confirmation |  to continue. |
| --- | ---------- | -------------------- | ------------- |
Tool execution failed due to
| tool |     | Yes, if configured. |     |
| ---- | --- | ------------------- | --- |
provider error.
Workflow logic error (e.g.
| workflow |     | No; fix skill definition. |     |
| -------- | --- | ------------------------- | --- |
undefined step, bad mapping).
Tool did not respond within the
| timeout |     | Yes, if configured. |     |
| ------- | --- | ------------------- | --- |
allocated time.
External API returned an
| external_api |     | Possibly; depends on provider and policy. |     |
| ------------ | --- | ----------------------------------------- | --- |
unrecoverable error.
Each error should include a  code ,  message , optional  details , a  recoverable  flag, and a
suggested_action . The suggested action could be to retry, adjust input, or update permissions.
Example Workflow
Below is an example of a simplified workflow for the video director skill. It follows the manifest example in
| skill-manifest-spec.md | .   |     |     |
| ---------------------- | --- | --- | --- |
steps:
- id: validate_prompt
| type: validation           |     |     |     |
| -------------------------- | --- | --- | --- |
| action: ensurePromptLength |     |     |     |
on:
| success: | retrieve_context |     |     |
| -------- | ---------------- | --- | --- |
| failure: | fail_validation  |     |     |
- id: retrieve_context
| type: tool_call |                    |     |     |
| --------------- | ------------------ | --- | --- |
| tool_id:        | rag_retrieval_tool |     |     |
input_mapping:
| query:  | $.input.prompt |     |     |
| ------- | -------------- | --- | --- |
| topK: 3 |                |     |     |
output_mapping:
| context: | $.output.items |     |     |
| -------- | -------------- | --- | --- |
on:
| success: | generate_video   |     |     |
| -------- | ---------------- | --- | --- |
| failure: | normalize_result |     |     |
- id: generate_video
| type: tool_call |                            |     |     |
| --------------- | -------------------------- | --- | --- |
| tool_id:        | mock_video_generation_tool |     |     |
4

input_mapping:
prompt: $.input.prompt
duration: $.input.duration
context: $.steps.retrieve_context.output.context
output_mapping:
title: $.output.title
summary: $.output.summary
file_id: $.output.file_id
on:
success: normalize_result
failure: normalize_result
- id: normalize_result
type: service_call
action: svc.result_normalizer.completed
on:
success: success_completed
failure: fail_workflow
- id: success_completed
type: end
- id: fail_validation
type: end
- id: fail_workflow
type: end
This workflow first validates the prompt, retrieves context from RAG, generates a video, then normalizes
and returns the result. Errors propagate to appropriate end states.
Notes
ò Keep workflows declarative and avoid embedding business logic into step identifiers. Complex logic
should be encapsulated in tools or sub?workflows.
ò Avoid long chains of retriesùprefer to tune individual tool reliability.
ò Always consider compensation for side?effecting steps.
ò Document each step clearly to aid maintainability and auditing.
5
