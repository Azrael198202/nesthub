from __future__ import annotations

from typing import Any


class MemoryPromotionService:
    """Promote high-value execution results into long-term NestHub memory layers."""

    MIN_CONTENT_LENGTH = 12
    MIN_TOKEN_COUNT = 3
    MAX_EVIDENCE_LENGTH = 200
    DUPLICATE_SEARCH_TOP_K = 3

    def __init__(
        self,
        *,
        semantic_policy_store: Any,
        vector_store: Any,
        generated_artifact_store: Any | None = None,
    ) -> None:
        self.semantic_policy_store = semantic_policy_store
        self.vector_store = vector_store
        self.generated_artifact_store = generated_artifact_store

    def promote_execution_result(
        self,
        *,
        task: dict[str, Any],
        context: dict[str, Any],
        execution_result: dict[str, Any],
    ) -> dict[str, Any]:
        final_output = execution_result.get("final_output") or {}
        trace_id = str(context.get("trace_id") or execution_result.get("trace_id") or "").strip()
        session_id = str(context.get("session_id") or "").strip()
        promotions: list[dict[str, Any]] = []

        analyze_document = final_output.get("analyze_document") or {}
        if str(analyze_document.get("status") or "") == "completed":
            promotion = self._promote_document_analysis(
                task=task,
                context=context,
                payload=analyze_document,
                trace_id=trace_id,
                session_id=session_id,
            )
            if promotion:
                promotions.append(promotion)

        manage_information_agent = final_output.get("manage_information_agent") or {}
        if manage_information_agent:
            promotion = self._promote_information_agent(
                task=task,
                context=context,
                payload=manage_information_agent,
                trace_id=trace_id,
                session_id=session_id,
            )
            if promotion:
                promotions.append(promotion)

        summary = {
            "promoted": bool(promotions),
            "promotion_count": len(promotions),
            "items": promotions,
            "skipped": [],
        }

        if promotions and self.generated_artifact_store is not None and trace_id:
            artifact_path = self.generated_artifact_store.persist(
                "code",
                f"memory_promotion_{trace_id}",
                summary,
            )
            summary["artifact_path"] = str(artifact_path)

        return summary

    def _promote_document_analysis(
        self,
        *,
        task: dict[str, Any],
        context: dict[str, Any],
        payload: dict[str, Any],
        trace_id: str,
        session_id: str,
    ) -> dict[str, Any] | None:
        requested_action = str(payload.get("requested_action") or "analyze")
        if requested_action == "translate":
            knowledge_text = str(payload.get("translation") or "").strip()
        else:
            knowledge_text = str(payload.get("summary") or payload.get("message") or "").strip()
        if not self._is_promotable_text(knowledge_text):
            return None

        source_documents = list(payload.get("source_documents") or [])
        request_text = str(task.get("input_text") or "").strip()
        namespace = "document_analysis"
        item_id = f"memory_promotion:{trace_id or session_id or requested_action}:document"
        duplicate = self._find_duplicate(namespace=namespace, content=knowledge_text)
        if duplicate:
            return {
                "kind": "document_analysis",
                "requested_action": requested_action,
                "vector_item_id": duplicate.get("id"),
                "source_documents": source_documents,
                "status": "deduplicated",
                "inspection": self._build_inspection_payload(namespace=namespace, content=knowledge_text),
            }
        vector_record = self.vector_store.add_knowledge(
            namespace=namespace,
            content=knowledge_text,
            metadata={
                "trace_id": trace_id,
                "session_id": session_id,
                "task_intent": str(task.get("intent") or ""),
                "requested_action": requested_action,
                "source_documents": source_documents,
                "target_language": str(payload.get("target_language") or ""),
            },
            item_id=item_id,
        )
        self.semantic_policy_store.record_intent_knowledge(
            f"memory_promotion:{trace_id}:document_analysis",
            {
                "intent": str(task.get("intent") or "file_upload_task"),
                "domain": str(task.get("domain") or "multimodal_ops"),
                "summary": knowledge_text,
                "requested_action": requested_action,
                "source_documents": source_documents,
                "trace_id": trace_id,
                "session_id": session_id,
                "request_text": request_text,
                "output_requirements": ["text"],
                "constraints": {"memory_promoted": True},
            },
            source="memory_promotion_service",
            confidence=0.9,
            evidence=knowledge_text[: self.MAX_EVIDENCE_LENGTH],
        )
        return {
            "kind": "document_analysis",
            "requested_action": requested_action,
            "vector_item_id": vector_record.get("id"),
            "source_documents": source_documents,
            "status": "promoted",
            "inspection": self._build_inspection_payload(namespace=namespace, content=knowledge_text),
        }

    def _promote_information_agent(
        self,
        *,
        task: dict[str, Any],
        context: dict[str, Any],
        payload: dict[str, Any],
        trace_id: str,
        session_id: str,
    ) -> dict[str, Any] | None:
        agent = payload.get("agent") if isinstance(payload.get("agent"), dict) else {}
        workflow_state = payload.get("workflow_state") if isinstance(payload.get("workflow_state"), dict) else {}
        knowledge = payload.get("knowledge")
        summary_parts = [
            str(payload.get("message") or "").strip(),
            str((agent or {}).get("name") or "").strip(),
            str((agent or {}).get("role") or "").strip(),
            str(workflow_state.get("summary") or "").strip(),
        ]
        if isinstance(knowledge, dict):
            summary_parts.append(self._render_dict_as_text(knowledge))
        knowledge_text = " | ".join(part for part in summary_parts if part)
        if not self._is_promotable_text(knowledge_text):
            return None

        namespace = "information_agent"
        facts = self._extract_information_agent_facts(
            task=task,
            agent=agent,
            workflow_state=workflow_state,
            payload=payload,
            trace_id=trace_id,
            session_id=session_id,
        )
        experiences = self._extract_information_agent_experiences(
            task=task,
            agent=agent,
            workflow_state=workflow_state,
            payload=payload,
            trace_id=trace_id,
            session_id=session_id,
        )
        duplicate = self._find_duplicate(namespace=namespace, content=knowledge_text)
        if duplicate:
            return {
                "kind": "information_agent",
                "vector_item_id": duplicate.get("id"),
                "agent_id": str((agent or {}).get("agent_id") or payload.get("agent_id") or ""),
                "status": "deduplicated",
                "facts": facts,
                "experiences": experiences,
                "inspection": self._build_inspection_payload(namespace=namespace, content=knowledge_text),
            }

        item_id = f"memory_promotion:{trace_id or session_id}:information_agent"
        vector_record = self.vector_store.add_knowledge(
            namespace=namespace,
            content=knowledge_text,
            metadata={
                "trace_id": trace_id,
                "session_id": session_id,
                "task_intent": str(task.get("intent") or ""),
                "agent_id": str((agent or {}).get("agent_id") or payload.get("agent_id") or ""),
            },
            item_id=item_id,
        )
        for index, fact in enumerate(facts, start=1):
            fact_text = self._render_dict_as_text(fact)
            self.vector_store.add_knowledge(
                namespace="information_agent_fact",
                content=fact_text,
                metadata=fact,
                item_id=f"memory_promotion:{trace_id or session_id}:information_agent:fact:{index}",
            )
        for index, experience in enumerate(experiences, start=1):
            self.semantic_policy_store.record_intent_knowledge(
                f"memory_promotion:{trace_id}:information_agent:experience:{index}",
                {
                    "intent": str(task.get("intent") or "create_information_agent"),
                    "domain": str(task.get("domain") or "general"),
                    "summary": experience.get("summary", ""),
                    "experience": experience,
                    "trace_id": trace_id,
                    "session_id": session_id,
                    "request_text": str(task.get("input_text") or "").strip(),
                    "output_requirements": ["text"],
                    "constraints": {"memory_promoted": True, "knowledge_type": "experience"},
                },
                source="memory_promotion_service",
                confidence=0.88,
                evidence=str(experience.get("summary") or "")[: self.MAX_EVIDENCE_LENGTH],
            )
        self.semantic_policy_store.record_intent_knowledge(
            f"memory_promotion:{trace_id}:information_agent",
            {
                "intent": str(task.get("intent") or "create_information_agent"),
                "domain": str(task.get("domain") or "general"),
                "summary": knowledge_text,
                "agent": agent,
                "workflow_state": workflow_state,
                "facts": facts,
                "experiences": experiences,
                "trace_id": trace_id,
                "session_id": session_id,
                "request_text": str(task.get("input_text") or "").strip(),
                "output_requirements": ["text"],
                "constraints": {"memory_promoted": True},
            },
            source="memory_promotion_service",
            confidence=0.88,
            evidence=knowledge_text[: self.MAX_EVIDENCE_LENGTH],
        )
        return {
            "kind": "information_agent",
            "vector_item_id": vector_record.get("id"),
            "agent_id": str((agent or {}).get("agent_id") or payload.get("agent_id") or ""),
            "status": "promoted",
            "facts": facts,
            "experiences": experiences,
            "inspection": self._build_inspection_payload(namespace=namespace, content=knowledge_text),
        }

    def _extract_information_agent_facts(
        self,
        *,
        task: dict[str, Any],
        agent: dict[str, Any],
        workflow_state: dict[str, Any],
        payload: dict[str, Any],
        trace_id: str,
        session_id: str,
    ) -> list[dict[str, Any]]:
        facts: list[dict[str, Any]] = []
        agent_id = str(agent.get("agent_id") or payload.get("agent_id") or "")
        entity_label = str(agent.get("knowledge_entity_label") or workflow_state.get("entity_label") or "信息条目")
        schema_fields = [str(item) for item in list(agent.get("schema_fields") or []) if str(item).strip()]
        if agent_id or schema_fields:
            facts.append(
                {
                    "type": "information_agent_definition",
                    "agent_id": agent_id,
                    "entity_label": entity_label,
                    "profile": str(agent.get("profile") or workflow_state.get("profile") or "generic_information"),
                    "schema_fields": schema_fields,
                    "activation_keywords": [str(item) for item in list(agent.get("activation_keywords") or workflow_state.get("activation_keywords") or []) if str(item).strip()],
                    "query_aliases": workflow_state.get("query_aliases") if isinstance(workflow_state.get("query_aliases"), dict) else {},
                    "trace_id": trace_id,
                    "session_id": session_id,
                }
            )
        knowledge = payload.get("knowledge")
        if isinstance(knowledge, dict) and knowledge:
            facts.append(
                {
                    "type": "information_agent_record",
                    "agent_id": agent_id,
                    "entity_label": entity_label,
                    "record": knowledge,
                    "record_keys": sorted(str(key) for key in knowledge.keys()),
                    "trace_id": trace_id,
                    "session_id": session_id,
                }
            )
        return facts

    def _extract_information_agent_experiences(
        self,
        *,
        task: dict[str, Any],
        agent: dict[str, Any],
        workflow_state: dict[str, Any],
        payload: dict[str, Any],
        trace_id: str,
        session_id: str,
    ) -> list[dict[str, Any]]:
        experiences: list[dict[str, Any]] = []
        dialog_state = payload.get("dialog_state") if isinstance(payload.get("dialog_state"), dict) else {}
        stage = str(dialog_state.get("stage") or "")
        if stage:
            experiences.append(
                {
                    "type": "information_agent_runtime_experience",
                    "summary": f"information agent stage {stage} completed for {str(agent.get('role') or workflow_state.get('entity_label') or 'information agent')}",
                    "task_intent": str(task.get("intent") or ""),
                    "stage": stage,
                    "agent_id": str(agent.get("agent_id") or payload.get("agent_id") or ""),
                    "trace_id": trace_id,
                    "session_id": session_id,
                }
            )
        knowledge = payload.get("knowledge")
        if isinstance(knowledge, dict) and knowledge:
            experiences.append(
                {
                    "type": "information_agent_capture_pattern",
                    "summary": f"captured information agent knowledge with fields: {', '.join(sorted(str(key) for key in knowledge.keys()))}",
                    "task_intent": str(task.get("intent") or "capture_agent_knowledge"),
                    "record_keys": sorted(str(key) for key in knowledge.keys()),
                    "agent_id": str(agent.get("agent_id") or payload.get("agent_id") or ""),
                    "trace_id": trace_id,
                    "session_id": session_id,
                }
            )
        return experiences

    def _is_promotable_text(self, text: str) -> bool:
        normalized = " ".join(text.split())
        token_count = len(self._tokenize(normalized))
        if len(normalized) < self.MIN_CONTENT_LENGTH and token_count < self.MIN_TOKEN_COUNT:
            return False
        if normalized.lower() in {"ok", "done", "success", "已完成", "完成"}:
            return False
        return True

    def _tokenize(self, text: str) -> list[str]:
        return [token for token in str(text).replace("|", " ").split() if token]

    def _find_duplicate(self, *, namespace: str, content: str) -> dict[str, Any] | None:
        try:
            candidates = self.vector_store.search(content, top_k=self.DUPLICATE_SEARCH_TOP_K, namespace=namespace)
        except Exception:
            return None
        normalized = self._normalize_text(content)
        for candidate in candidates:
            candidate_content = str(candidate.get("content") or "")
            if self._normalize_text(candidate_content) == normalized:
                return candidate
        return None

    def _build_inspection_payload(self, *, namespace: str, content: str) -> dict[str, Any]:
        similar_items = []
        try:
            matches = self.vector_store.search(content, top_k=self.DUPLICATE_SEARCH_TOP_K, namespace=namespace)
            for match in matches:
                similar_items.append(
                    {
                        "id": match.get("id"),
                        "namespace": match.get("namespace"),
                        "content_preview": str(match.get("content") or "")[:120],
                    }
                )
        except Exception:
            similar_items = []
        return {
            "namespace": namespace,
            "query_preview": content[:120],
            "similar_items": similar_items,
        }

    def _normalize_text(self, text: str) -> str:
        return " ".join(str(text).split()).strip().lower()

    def _render_dict_as_text(self, payload: dict[str, Any]) -> str:
        parts: list[str] = []
        for key, value in payload.items():
            if value in (None, "", [], {}):
                continue
            parts.append(f"{key}: {value}")
        return " | ".join(parts)