## Contexts
Web applications are not like regular programs. At any point in the sequential execution of instructions 
there is a large number of, usually implicit, horizontal factors that can influence behaviour or the interpretation 
of correctness. For example:

* What environment am I operating in?
* What boundaries am I crossing?
* What user or tenant am I acting on behalf of?
* Do they have feature flags enabled or are they enrolled in any A/B tests?
* Is it safe to perform this operation at this point in the execution? 
When we try to deal with these factors ad-hoc, the codebase becomes a mess of interleaved
business logic and application control. It becomes intractable to ensure that all parts 
of the codebase, even in the same execution path, are aligned on these implicit factors.
Better our logic has shared, direct access to any contextual information it needs.
The primary contexts in **Unrest** are the `query` and `mutate` contexts. 

An explicit distinction between reads and writes provides a primitive for higher-level functionality:
* **Correctness**. State mutations in a `query` context can be caught at runtime. 
* **Access control**. Permissions can be enforced throughout an execution trace.
* **Scalability**. Reads can be transparently redirected to replicas. 
* **Safety**. Code can be developed and debugged against production datastores.
In addition to propagating contextual information throughout the execution path, 
**Unrest** ensures that it is also propogated to your logs for later analysis.