# Implementation Plan

- [x] 1. Set up project structure and packaging
  - [x] 1.1 Create project skeleton with pyproject.toml
    - Create `necrostack/` package directory structure
    - Create `pyproject.toml` with metadata, dependencies (pydantic), and optional redis extra
    - Create `README.md` with project overview and features
    - Create `.gitignore` for Python projects
    - Add `py.typed` marker for PEP 561
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 1.2 Set up testing infrastructure
    - Create `tests/` directory with `conftest.py`
    - Configure pytest and hypothesis in pyproject.toml
    - Create Hypothesis strategies for Event generation
    - _Requirements: 7.1_

- [x] 2. Implement Event model
  - [x] 2.1 Create Event base class
    - Implement `Event` class with `id`, `timestamp`, `event_type`, `payload` fields
    - Configure Pydantic frozen model for immutability
    - Add `model_dump_jsonable()` method for serialization
    - _Requirements: 1.1, 1.3, 1.4_

  - [x] 2.2 Write property test for Event serialization round-trip
    - **Property 1: Event Serialization Round-Trip**
    - **Validates: Requirements 1.4, 1.5**

  - [x] 2.3 Write property test for Event immutability and auto-fields
    - **Property 2: Event Immutability and Auto-Fields**
    - **Validates: Requirements 1.3**

  - [x] 2.4 Write property test for invalid Event rejection
    - **Property 3: Invalid Event Rejection**
    - **Validates: Requirements 1.2**

- [x] 3. Implement Organ base class
  - [x] 3.1 Create Organ abstract base class
    - Implement `Organ` ABC with `listens_to` class variable
    - Define abstract `handle()` method with flexible return type
    - _Requirements: 2.1, 2.2_

- [ ] 4. Implement Backend protocol and in-memory backend
  - [x] 4.1 Create Backend protocol
    - Define `Backend` protocol with `enqueue`, `pull`, `ack`, `close` methods
    - _Requirements: 4.1_

  - [x] 4.2 Implement InMemoryBackend
    - Create `InMemoryBackend` using `asyncio.Queue`
    - Implement FIFO enqueue/pull with timeout support
    - Implement `close()` to clear queue
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 4.3 Write property test for Backend FIFO ordering
    - **Property 9: Backend FIFO Ordering**
    - **Validates: Requirements 4.2**

- [ ] 5. Implement Spine dispatcher
  - [ ] 5.1 Create Spine class with organ registration
    - Implement `Spine.__init__()` accepting organs, backend, max_steps
    - Build internal routing table from organ `listens_to`
    - Validate organ handler signatures at registration
    - _Requirements: 3.1, 7.2_

  - [ ] 5.2 Write property test for invalid Organ signature detection
    - **Property 10: Invalid Organ Signature Detection**
    - **Validates: Requirements 7.2**

  - [ ] 5.3 Implement event emission and handler invocation
    - Implement `emit()` to enqueue events
    - Implement `_invoke_handler()` supporting sync and async handlers
    - Handle handler return values (Event, list, None)
    - _Requirements: 2.3, 2.4, 2.5, 2.6, 2.7_

  - [ ] 5.4 Write property test for Event routing correctness
    - **Property 4: Event Routing Correctness**
    - **Validates: Requirements 2.2, 2.3, 3.3**

  - [ ] 5.5 Write property test for handler return value processing
    - **Property 5: Handler Return Value Processing**
    - **Validates: Requirements 2.6, 2.7**

  - [ ] 5.6 Implement main processing loop
    - Implement `run()` with event pull/dispatch loop
    - Add max_steps guard for loop termination
    - Implement graceful `stop()` method
    - _Requirements: 3.2, 3.6, 3.7_

  - [ ] 5.7 Write property test for Organ invocation order
    - **Property 6: Organ Invocation Order**
    - **Validates: Requirements 3.4**

  - [ ] 5.8 Implement error handling in processing loop
    - Catch and log handler exceptions
    - Continue processing after handler failures
    - _Requirements: 3.5_

  - [ ] 5.9 Write property test for error resilience
    - **Property 7: Error Resilience**
    - **Validates: Requirements 3.5**

  - [ ] 5.10 Write property test for max-steps termination
    - **Property 8: Max-Steps Termination**
    - **Validates: Requirements 3.7**

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement Redis Streams backend (MVP-Light)
  - [ ] 7.1 Create RedisBackend class
    - Implement connection to Redis using redis-py async client
    - Implement `enqueue()` using XADD
    - Implement `pull()` using XREAD with blocking timeout
    - Implement `ack()` as no-op for MVP
    - Implement `close()` to close connection
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ] 7.2 Write integration tests for Redis backend
    - Test enqueue/pull round-trip with real Redis
    - Test timeout behavior on empty stream
    - Test connection handling
    - _Requirements: 5.1, 5.2, 5.3_

- [ ] 8. Final Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
