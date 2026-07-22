#!/usr/bin/env python3
"""Seed the ScoutOS database with rich demo data for the Mission Control dashboard.

Usage:
    cd /home/harshdev/flytbase_hackthon
    source .venv/bin/activate
    python scripts/seed_demo_data.py

This creates 5 demo companies with complete lifecycle data across all agent phases.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.db import models
from app.db.session import SessionLocal
from app.intelligence import CompanyIntelligenceBriefBuilder

# ── Helpers ─────────────────────────────────────────────────────────────

_now = datetime.now(timezone.utc)


def _dt(**delta) -> datetime:
    return _now - timedelta(**delta)


def _id() -> uuid.UUID:
    return uuid.uuid4()


# ── Demo data ───────────────────────────────────────────────────────────

COMPANIES = [
    {
        "name": "SkyGrid Inc.",
        "domain": "skygrid.io",
        "industry": "Drone Technology",
        "employee_count": 320,
        "location": "San Francisco, CA",
        "profile_data": {
            "description": "SkyGrid provides autonomous drone fleet management software for enterprise logistics, agriculture, and inspection use cases. Their platform enables real-time fleet tracking, automated flight planning, and AI-powered data analysis.",
            "business_signals": [
                "hiring robotics engineers",
                "raised Series B ($40M)",
                "expanding to EU market",
                "launched drone-as-a-service"
            ],
            "technology_signals": ["Python", "React", "AWS", "PostgreSQL", "Kubernetes"],
            "pain_points": [
                "manual flight planning at scale",
                "regulatory compliance overhead",
                "fragmented data pipeline"
            ],
            "flytbase_relevance": "Direct competitor overlap — SkyGrid's fleet management complements FlytBase's drone-agnostic ground control software. Partnership opportunity in enterprise logistics.",
        },
    },
    {
        "name": "AeroVista",
        "domain": "aerovista.tech",
        "industry": "Aerial Imaging & Surveying",
        "employee_count": 85,
        "location": "Austin, TX",
        "profile_data": {
            "description": "AeroVista specializes in high-resolution aerial surveying for construction, real estate, and infrastructure inspection. Uses drones for orthomosaic mapping and 3D modeling.",
            "business_signals": [
                "won contract with major construction firm",
                "hiring GIS specialists",
                "developed proprietary stitching software"
            ],
            "technology_signals": ["GIS", "Python", "C++", "PostGIS"],
            "pain_points": [
                "limited automation in flight planning",
                "manual data handoff to clients",
                "no real-time collaboration"
            ],
            "flytbase_relevance": "Strong integration opportunity — FlytBase's mission planning and livestreaming would streamline AeroVista's surveying workflows.",
        },
    },
    {
        "name": "DroneFleet Logistics",
        "domain": "dronefleet.com",
        "industry": "Logistics & Delivery",
        "employee_count": 210,
        "location": "Chicago, IL",
        "profile_data": {
            "description": "DroneFleet operates a last-mile delivery network using autonomous drones for medical supplies, food delivery, and e-commerce logistics in urban and suburban areas.",
            "business_signals": [
                "raised Series A ($18M)",
                "partnered with major pharmacy chain",
                "launched in 3 new cities"
            ],
            "technology_signals": ["Go", "React Native", "GCP", "Redis", "Terraform"],
            "pain_points": [
                "fleet scalability challenges",
                "airspace deconfliction at scale",
                "battery swap logistics"
            ],
            "flytbase_relevance": "High relevance — FlyTbase's fleet management and remote drone operations capabilities directly address DroneFleet's scalability challenges.",
        },
    },
    {
        "name": "AirMap Technologies",
        "domain": "airmap.tech",
        "industry": "Airspace Management",
        "employee_count": 55,
        "location": "Berlin, Germany",
        "profile_data": {
            "description": "AirMap builds airspace intelligence and UTM (Unmanned Traffic Management) solutions for drone operators, airports, and regulatory authorities across Europe.",
            "business_signals": [
                "participating in EU drone regulation pilot",
                "hiring airspace engineers",
                "grant from European Innovation Council"
            ],
            "technology_signals": ["Java", "Angular", "Azure", "Cassandra"],
            "pain_points": [
                "integration with multiple drone platforms",
                "real-time airspace data processing",
                "regulatory reporting automation"
            ],
            "flytbase_relevance": "Strategic partnership — AirMap's UTM integration would expand FlyTbase's European market presence and regulatory compliance features.",
        },
    },
    {
        "name": "PrecisionAg Drones",
        "domain": "precisionag.io",
        "industry": "Agriculture Technology",
        "employee_count": 42,
        "location": "Bangalore, India",
        "profile_data": {
            "description": "PrecisionAg provides drone-based crop monitoring, spraying, and yield analysis services for Indian farms. Combines multispectral imaging with ML for actionable insights.",
            "business_signals": [
                "growing rapidly in Indian market",
                "partnered with agricultural universities",
                "developed ML crop disease detection"
            ],
            "technology_signals": ["Python", "TensorFlow", "React", "PostgreSQL"],
            "pain_points": [
                "manual drone operation at scale",
                "limited remote operations capability",
                "need for automated reporting"
            ],
            "flytbase_relevance": "High growth potential — PrecisionAg is ripe for FlyTbase's remote drone operations and automation features to scale their service offerings.",
        },
    },
]

# ── Qualification scores per company ───────────────────────────────────

QUALIFICATION_DATA = [
    {
        "company_name": "SkyGrid Inc.",
        "overall_score": 91,
        "icp_match_score": 95,
        "buying_signal_score": 88,
        "company_fit_score": 90,
        "priority": "HOT",
        "reasons": [
            "Drone fleet operations detected — direct FlytBase fit",
            "Enterprise customer base with Series B funding",
            "Hiring robotics engineers — expansion phase",
            "Expanding to EU market — needs remote ops",
            "Technology stack aligns with FlytBase platform"
        ],
        "risks": [
            "Could be evaluating competitor platforms"
        ],
        "recommended_urgency": "This week",
        "recommended_sales_angle": "Position FlytBase as a force multiplier for their fleet scalability — emphasize remote operations and automation API",
    },
    {
        "company_name": "AeroVista",
        "overall_score": 73,
        "icp_match_score": 80,
        "buying_signal_score": 65,
        "company_fit_score": 75,
        "priority": "WARM",
        "reasons": [
            "Active in aerial surveying — strong use case",
            "Mid-size company with room to scale",
            "Developing proprietary software — needs API integration"
        ],
        "risks": [
            "May have existing vendor relationships",
            "Limited public buying signals"
        ],
        "recommended_urgency": "This month",
        "recommended_sales_angle": "Focus on FlytBase's mission planning automation and real-time streaming for surveying workflows",
    },
    {
        "company_name": "DroneFleet Logistics",
        "overall_score": 85,
        "icp_match_score": 88,
        "buying_signal_score": 82,
        "company_fit_score": 85,
        "priority": "HOT",
        "reasons": [
            "Last-mile drone delivery at scale — perfect use case",
            "Recent funding and rapid expansion",
            "Fleet scalability challenges align with FlytBase"
        ],
        "risks": [
            "Heavy existing tech investment (GCP, Go, Terraform)"
        ],
        "recommended_urgency": "This week",
        "recommended_sales_angle": "Showcase fleet management and remote operations for scaling their delivery network — integration with their GCP stack",
    },
    {
        "company_name": "AirMap Technologies",
        "overall_score": 67,
        "icp_match_score": 70,
        "buying_signal_score": 55,
        "company_fit_score": 72,
        "priority": "WARM",
        "reasons": [
            "Airspace management — strategic complement to FlytBase",
            "European market presence — expansion opportunity",
            "EU regulation pilot participation — early mover"
        ],
        "risks": [
            "More of a partnership than a direct customer",
            "Early-stage with limited revenue signals"
        ],
        "recommended_urgency": "This quarter",
        "recommended_sales_angle": "Position as strategic partnership — FlytBase fleet ops + AirMap UTM integration for European market",
    },
    {
        "company_name": "PrecisionAg Drones",
        "overall_score": 59,
        "icp_match_score": 65,
        "buying_signal_score": 45,
        "company_fit_score": 62,
        "priority": "WARM",
        "reasons": [
            "Agriculture drone operations — growing segment",
            "Indian market — large untapped opportunity",
            "ML development capability — advanced user"
        ],
        "risks": [
            "Small company with limited budget",
            "Price sensitivity expected in Indian market",
            "No public funding signals"
        ],
        "recommended_urgency": "This month",
        "recommended_sales_angle": "Highlight cost savings from automation and remote operations — position as growth enabler for their service expansion",
    },
]

# ── Outreach drafts per company ────────────────────────────────────────

OUTREACH_DATA = [
    {
        "company_name": "SkyGrid Inc.",
        "strategy_channel": "email",
        "strategy_urgency": "This week",
        "strategy_reasoning": "SkyGrid is actively scaling with Series B funding and EU expansion. High ICP match score (95) suggests immediate outreach priority.",
        "company_hook": "Your Series B and EU expansion plans signal exciting growth — and with fleet scale comes new operational challenges that we at FlytBase specialize in solving.",
        "detected_pain_point": "Manual flight planning at scale — your team is likely spending too much time on route planning and fleet coordination that could be automated.",
        "flytbase_value_proposition": "FlytBase's drone-agnostic fleet management platform automates mission planning, enables remote operations, and provides a unified API for your existing tech stack.",
        "draft_subject": "Scaling SkyGrid's drone fleet operations — a partnership opportunity",
        "draft_body": "Hi there,\n\nI've been following SkyGrid's impressive growth — the Series B funding and EU market expansion are exciting milestones.\n\nAs you scale your autonomous drone fleet, we've seen similar companies face challenges with:\n• Manual flight planning that doesn't scale\n• Regulatory compliance across multiple regions\n• Fragmented data pipelines between drones and analysis tools\n\nAt FlytBase, we built a drone-agnostic ground control platform that addresses exactly these challenges:\n\n• Automated mission planning and fleet coordination\n• Remote drone operations from anywhere\n• Unified API for integrating with your existing stack (Python, React, AWS)\n• Real-time streaming and data pipeline automation\n\nI'd love to show you how we're helping companies like yours reduce fleet coordination time by 60%.\n\nAre you open to a 20-minute demo this week?\n\nBest,\n[Jane from FlytBase]",
        "follow_up_suggestion": "If no reply in 3 days, follow up with a case study of a similar drone fleet operator who scaled from 50 to 500 drones using FlytBase.",
    },
    {
        "company_name": "DroneFleet Logistics",
        "strategy_channel": "email",
        "strategy_urgency": "This week",
        "strategy_reasoning": "DroneFleet is actively scaling with new city launches and a major pharmacy partnership. Fleet scalability is their stated pain point.",
        "company_hook": "Expanding to 3 new cities while partnering with a major pharmacy chain — your fleet scalability challenge is exactly what FlytBase was built to solve.",
        "detected_pain_point": "Fleet scalability — coordinating autonomous deliveries across multiple cities requires sophisticated fleet management that off-the-shelf solutions struggle to provide.",
        "flytbase_value_proposition": "FlytBase's fleet management platform enables you to coordinate delivery drones across cities from a single dashboard, with automated airspace deconfliction and battery management.",
        "draft_subject": "Scaling DroneFleet's delivery network with intelligent fleet ops",
        "draft_body": "Hi there,\n\nCongratulations on the new city launches and the pharmacy partnership — impressive growth trajectory!\n\nAs you scale your last-mile delivery network, we know that fleet coordination becomes exponentially more complex. We've built FlytBase to handle exactly this challenge:\n\n• Single-dashboard fleet management across multiple cities\n• Automated airspace deconfliction\n• Battery and resource optimization\n• Remote operations to reduce pilot costs\n\nGiven your GCP stack, our API-first approach would integrate seamlessly with your existing infrastructure.\n\nWould you have 20 minutes this week to see how we're helping delivery networks scale their operations?\n\nBest,\n[Jane from FlytBase]",
        "follow_up_suggestion": "Send a technical whitepaper on fleet scalability after 5 days if no response.",
    },
    {
        "company_name": "AeroVista",
        "strategy_channel": "email",
        "strategy_urgency": "This month",
        "strategy_reasoning": "AeroVista is growing steadily with a major construction contract. Their surveying workflow could benefit from FlytBase's mission planning automation.",
        "company_hook": "Your new construction contract is a great win — and our mission planning tools could help you deliver surveys faster and more efficiently.",
        "detected_pain_point": "Manual data handoff and limited automation in flight planning are likely slowing down your surveying workflow.",
        "flytbase_value_proposition": "FlytBase's automated mission planning and real-time streaming enable faster survey cycles and seamless data handoff to clients.",
        "draft_subject": "Streamlining AeroVista's aerial surveying workflow",
        "draft_body": "Hi there,\n\nCongratulations on the major construction contract — that's a great validation of AeroVista's surveying capabilities.\n\nWe've been working with aerial surveying companies to address the bottlenecks you're likely facing:\n\n• Manual flight planning for each survey site\n• Slow data handoff between field operations and clients\n• Limited real-time collaboration during missions\n\nFlytBase provides:\n\n• One-click automated mission planning\n• Real-time video streaming for client demos\n• API-driven data pipeline for seamless handoff to your GIS tools\n• Remote operation capabilities to reduce field pilot costs\n\nWould you have time for a quick call to see how this could fit your workflow?\n\nBest,\n[Jane from FlytBase]",
        "follow_up_suggestion": "Share a case study of a surveying company that reduced mission planning time by 70% with FlytBase.",
    },
]

# ── Inbound messages ──────────────────────────────────────────────────

INBOUND_MESSAGES = [
    {
        "company_name": "SkyGrid Inc.",
        "from_name": "Sarah Chen",
        "from_email": "sarah@skygrid.io",
        "subject": "Re: Scaling SkyGrid's drone fleet operations",
        "body": "Hi Jane,\n\nThanks for reaching out. We're definitely interested in exploring ways to streamline our fleet operations. The EU expansion is creating some new challenges around remote management that we hadn't anticipated.\n\nCould you share more detail about how FlytBase handles multi-region regulatory compliance? That's a key concern for us.\n\nWould love to schedule a demo. How does next Tuesday at 2pm PT work?\n\nBest,\nSarah Chen\nHead of Operations, SkyGrid Inc.",
        "intent": "meeting_request",
        "sentiment": "positive",
        "urgency": "high",
        "lead_action": "schedule_demo",
        "suggested_reply_body": "Hi Sarah,\n\nGreat to hear from you! I'd be happy to dive into the multi-region compliance question — it's actually one of our core strengths.\n\nFor your EU expansion, FlytBase provides:\n• Geo-fencing and airspace rule enforcement per region\n• Automated compliance reporting for regulatory authorities\n• Configurable mission parameters for different regulatory zones\n• Remote operations with role-based access control\n\nNext Tuesday at 2pm PT works perfectly. I'll send a calendar invite shortly with a Zoom link.\n\nIn the meantime, I've attached a brief overview of our EU compliance capabilities.\n\nLooking forward to the conversation!\n\nBest,\nJane",
    },
    {
        "company_name": "SkyGrid Inc.",
        "from_name": "Sarah Chen",
        "from_email": "sarah@skygrid.io",
        "subject": "Re: Demo follow-up",
        "body": "Jane,\n\nThanks for the demo — really impressive platform. The team was particularly excited about the API integration capabilities and the real-time streaming.\n\nWe'd like to proceed with a trial. Can you set up a sandbox environment for us to evaluate with a small fleet (5-10 drones) over the next 30 days?\n\nAlso, could you connect us with your partnership team? We're interested in exploring a deeper integration.\n\nBest,\nSarah",
        "intent": "trial_request",
        "sentiment": "positive",
        "urgency": "medium",
        "lead_action": "provision_trial",
        "suggested_reply_body": "Hi Sarah,\n\nThat's wonderful to hear! I'm glad the team found value in the platform.\n\nAbsolutely — I'll get a sandbox environment set up for you today. You'll have access to:\n• Full fleet management for up to 10 drones\n• API access with comprehensive documentation\n• Real-time streaming and mission planning\n• 30-day trial with dedicated support\n\nI'll also connect you with our partnerships team — they'll reach out this week to explore the deeper integration opportunity.\n\nYou should receive the sandbox credentials within the hour. Let me know if you need anything else to get started!\n\nBest,\nJane",
    },
    {
        "company_name": "DroneFleet Logistics",
        "from_name": "Mike Torres",
        "from_email": "mike@dronefleet.com",
        "subject": "Question about fleet management API",
        "body": "Hi,\n\nWe're evaluating fleet management platforms and came across FlytBase. I have a few technical questions:\n\n1. Does your platform support real-time drone telemetry aggregation from mixed fleets?\n2. How does the API handle airspace deconfliction for simultaneous operations in the same area?\n3. What's the latency on remote command-and-control?\n\nWe're currently running on GCP with Go microservices, so API quality is critical for us.\n\nThanks,\nMike Torres\nCTO, DroneFleet Logistics",
        "intent": "technical_inquiry",
        "sentiment": "neutral",
        "urgency": "medium",
        "lead_action": "send_technical_info",
        "suggested_reply_body": "Hi Mike,\n\nGreat questions! Let me address each one:\n\n1. **Mixed fleet telemetry**: Yes — our platform is drone-agnostic and aggregates telemetry from any MAVLink-compatible drone. We support real-time telemetry streaming via WebSocket with configurable data pipelines.\n\n2. **Airspace deconfliction**: Our API includes a deconfliction engine that handles geofencing, altitude separation, and temporal scheduling for overlapping operation zones. It's designed for exactly your use case.\n\n3. **Latency**: We've measured sub-200ms latency for command-and-control in production deployments with 4G/5G connectivity. For critical operations, we support edge deployment for single-digit millisecond latency.\n\nGiven your GCP + Go stack, I think you'll appreciate our gRPC API and Go client SDK. We also integrate natively with GCP Pub/Sub for event-driven fleet operations.\n\nWould you like to schedule a technical deep-dive with our engineering team? They can walk through a reference architecture tailored to your setup.\n\nBest,\nJane from FlytBase",
    },
]

# ── Pipeline stage order ──────────────────────────────────────────────

PIPELINE_STAGES = [
    {"name": "new", "display_name": "New", "order": 1, "color": "#3b82f6"},
    {"name": "researching", "display_name": "Researching", "order": 2, "color": "#6366f1"},
    {"name": "qualified", "display_name": "Qualified", "order": 3, "color": "#06b6d4"},
    {"name": "outreach", "display_name": "Outreach", "order": 4, "color": "#14b8a6"},
    {"name": "meeting_scheduled", "display_name": "Meeting Scheduled", "order": 5, "color": "#22c55e"},
    {"name": "negotiation", "display_name": "Negotiation", "order": 6, "color": "#eab308"},
    {"name": "closed_won", "display_name": "Closed Won", "order": 7, "color": "#34d399"},
    {"name": "closed_lost", "display_name": "Closed Lost", "order": 8, "color": "#ef4444"},
]

# ── Company-to-Lead mapping with pipeline positions ──────────────────

LEADS_DATA = [
    {
        "company_name": "SkyGrid Inc.",
        "status": "meeting_scheduled",
        "score": 91,
        "score_reasoning": "High ICP match — drone fleet operations, Series B funding, EU expansion. Strong buying signals from hiring and product launches.",
        "pipeline_entered_days_ago": 14,
        "pipeline_entered_by": "agent",
        "pipeline_reason": "Lead qualified by QualificationAgent — score 91, HOT priority.",
        "contact_name": "Sarah Chen",
        "contact_email": "sarah@skygrid.io",
        "contact_title": "Head of Operations",
    },
    {
        "company_name": "DroneFleet Logistics",
        "status": "outreach",
        "score": 85,
        "score_reasoning": "Strong ICP match — delivery drone fleet, recent funding, scalability pain points clearly align with FlytBase.",
        "pipeline_entered_days_ago": 7,
        "pipeline_entered_by": "agent",
        "pipeline_reason": "Lead qualified by QualificationAgent — score 85, HOT priority.",
        "contact_name": "Mike Torres",
        "contact_email": "mike@dronefleet.com",
        "contact_title": "CTO",
    },
    {
        "company_name": "AeroVista",
        "status": "outreach",
        "score": 73,
        "score_reasoning": "Good ICP match — aerial surveying use case, growing company, strong technology fit.",
        "pipeline_entered_days_ago": 5,
        "pipeline_entered_by": "agent",
        "pipeline_reason": "Lead qualified by QualificationAgent — score 73, WARM priority.",
        "contact_name": "Emily Park",
        "contact_email": "emily@aerovista.tech",
        "contact_title": "VP of Operations",
    },
    {
        "company_name": "AirMap Technologies",
        "status": "qualified",
        "score": 67,
        "score_reasoning": "Moderate ICP match — strategic partnership potential, European market presence, but limited direct buying signals.",
        "pipeline_entered_days_ago": 10,
        "pipeline_entered_by": "agent",
        "pipeline_reason": "Lead qualified by QualificationAgent — score 67, WARM priority.",
        "contact_name": "Lena Weber",
        "contact_email": "lena@airmap.tech",
        "contact_title": "CEO",
    },
    {
        "company_name": "PrecisionAg Drones",
        "status": "researching",
        "score": 59,
        "score_reasoning": "Moderate ICP match — agri-drone segment is growing, but company size and budget constraints limit near-term potential.",
        "pipeline_entered_days_ago": 3,
        "pipeline_entered_by": "agent",
        "pipeline_reason": "Lead qualified by QualificationAgent — score 59, WARM priority.",
        "contact_name": "Raj Patel",
        "contact_email": "raj@precisionag.io",
        "contact_title": "Founder & CEO",
    },
]


def seed_database() -> None:
    """Run the seed script."""
    db = SessionLocal()

    print("🌱  Seeding ScoutOS demo data...\n")

    # ── 1. Create ICP Config ──────────────────────────────────────────
    icp = db.query(models.IcpConfig).filter(models.IcpConfig.is_active.is_(True)).first()
    if not icp:
        icp = models.IcpConfig(
            id=_id(),
            name="Default BDR ICP",
            description="Default Ideal Customer Profile for drone industry BDR outreach",
            industries=["Drone Technology", "Logistics & Delivery", "Agriculture Technology", "Aerial Imaging & Surveying"],
            min_employees=30,
            max_employees=1000,
            locations=["US", "EU", "India"],
            technology_signals=["Python", "React", "AWS", "Kubernetes", "PostgreSQL", "Go"],
            is_active=True,
            version=1,
        )
        db.add(icp)
        print("   ✅ Default ICP config created")
    else:
        print("   ℹ️  ICP config already exists, skipping")

    # ── 2. Create Pipeline Stages ─────────────────────────────────────
    existing_stages = db.query(models.PipelineStage).count()
    if existing_stages == 0:
        for stage_data in PIPELINE_STAGES:
            stage = models.PipelineStage(
                id=_id(),
                name=stage_data["name"],
                display_name=stage_data["display_name"],
                description=f"{stage_data['display_name']} stage",
                order=stage_data["order"],
                is_active=True,
                color=stage_data["color"],
            )
            db.add(stage)
        print("   ✅ 8 pipeline stages created")
    else:
        print(f"   ℹ️  {existing_stages} pipeline stages already exist, skipping")

    db.flush()

    # ── 3. Create Companies & Agents Tasks ────────────────────────────
    for company_data in COMPANIES:
        company_name = company_data["name"]
        existing = db.query(models.Company).filter(
            models.Company.name == company_name
        ).first()
        if existing:
            print(f"   ℹ️  '{company_name}' already exists, skipping")
            continue

        # Company
        company = models.Company(
            id=_id(),
            name=company_data["name"],
            domain=company_data["domain"],
            industry=company_data["industry"],
            employee_count=company_data["employee_count"],
            profile_data=company_data["profile_data"],
            created_at=_dt(days=30),
            updated_at=_dt(days=1),
        )
        db.add(company)
        db.flush()

        print(f"\n   🏢 Created company: {company.name}")

        # Contact
        lead_info = next(ld for ld in LEADS_DATA if ld["company_name"] == company_name)
        contact = models.Contact(
            id=_id(),
            company_id=company.id,
            first_name=lead_info["contact_name"].split()[0],
            last_name=lead_info["contact_name"].split()[-1],
            email=lead_info["contact_email"],
            title=lead_info["contact_title"],
        )
        db.add(contact)
        db.flush()

        # Lead
        lead = models.Lead(
            id=_id(),
            company_id=company.id,
            contact_id=contact.id,
            status=lead_info["status"],
            score=lead_info["score"],
            score_reasoning=lead_info["score_reasoning"],
            source="outbound",
            created_at=_dt(days=30),
            updated_at=_dt(days=1),
        )
        db.add(lead)
        db.flush()

        # ── Research Task ────────────────────────────────────────────────
        research_task = models.AgentTask(
            id=_id(),
            agent_type="research",
            status="completed",
            company_id=company.id,
            lead_id=lead.id,
            input_data={"company_name": company.name, "domain": company.domain},
            output_data={
                "summary": f"Researched {company.name} — {company_data['industry']} company with {company_data['employee_count']} employees.",
                "findings": company_data["profile_data"],
                "providers_used": "freebuff",
            },
            created_at=_dt(days=28),
            updated_at=_dt(days=27),
        )
        db.add(research_task)
        db.flush()

        # Research Logs
        _add_log(db, research_task.id, "research_started", "Starting research for company", {"company": company.name}, _dt(days=28, hours=2))
        _add_log(db, research_task.id, "tool_called", "Running web search for company details", {"tool": "simulated_web_search"}, _dt(days=28, hours=1))
        _add_log(db, research_task.id, "tool_completed", "Web search completed — 12 results", {"result_count": 12}, _dt(days=28))
        _add_log(db, research_task.id, "synthesis_started", "Synthesizing research findings", {}, _dt(days=28))
        _add_log(db, research_task.id, "report_created", "Research report generated", {"industry": company_data["industry"], "employee_count": company_data["employee_count"]}, _dt(days=27, hours=23))
        _add_log(db, research_task.id, "task_completed", "Research task completed successfully", {}, _dt(days=27))

        # Research Report
        report = models.ResearchReport(
            id=_id(),
            company_id=company.id,
            lead_id=lead.id,
            task_id=research_task.id,
            summary=f"Comprehensive research profile for {company.name} — a {company_data['industry']} company with {company_data['employee_count']} employees based in {company_data.get('location', 'N/A')}.",
            findings=company_data["profile_data"],
            sources=[
                {"url": f"https://{company.domain}/about", "title": f"{company.name} About"},
                {"url": f"https://{company.domain}/careers", "title": f"{company.name} Careers"},
                {"url": f"https://crunchbase.com/company/{company.domain.split('.')[0]}", "title": f"{company.name} Crunchbase"},
            ],
            provider="freebuff",
            created_at=_dt(days=27),
        )
        db.add(report)
        db.flush()

        print("      📋 Research report created")

        # ── Qualification Task ───────────────────────────────────────────
        qual_data = next(q for q in QUALIFICATION_DATA if q["company_name"] == company_name)
        qual_task = models.AgentTask(
            id=_id(),
            agent_type="qualification",
            status="completed",
            company_id=company.id,
            lead_id=lead.id,
            input_data={"company_name": company.name, "findings": company_data["profile_data"]},
            output_data=qual_data,
            created_at=_dt(days=26),
            updated_at=_dt(days=25),
        )
        db.add(qual_task)
        db.flush()

        _add_log(db, qual_task.id, "qualification_started", "Starting qualification process", {"company": company.name}, _dt(days=26, hours=2))
        _add_log(db, qual_task.id, "deterministic_scoring", "Computing deterministic ICP, size, location scores", {"industry": company_data["industry"]}, _dt(days=26, hours=1))
        _add_log(db, qual_task.id, "ai_evaluation_started", "Evaluating buying signals and pain points via LLM", {}, _dt(days=26))
        _add_log(db, qual_task.id, "ai_evaluation_completed", "AI evaluation complete — scores generated", {"overall_score": qual_data["overall_score"]}, _dt(days=26))
        _add_log(db, qual_task.id, "report_created", f"Qualification complete: {qual_data['priority']} priority", {"priority": qual_data["priority"]}, _dt(days=25))

        # Qualification Result
        qual_result = models.QualificationResult(
            id=_id(),
            task_id=qual_task.id,
            company_id=company.id,
            lead_id=lead.id,
            report_id=report.id,
            icp_config_id=icp.id,
            overall_score=qual_data["overall_score"],
            icp_match_score=qual_data["icp_match_score"],
            buying_signal_score=qual_data["buying_signal_score"],
            company_fit_score=qual_data["company_fit_score"],
            priority=qual_data["priority"],
            reasoning="Hybrid scoring: deterministic (industry, size, location) + AI (buying signals, pain points, FlytBase relevance)",
            reasons=qual_data["reasons"],
            risks=qual_data["risks"],
            recommended_urgency=qual_data["recommended_urgency"],
            recommended_sales_angle=qual_data["recommended_sales_angle"],
            icp_inline_config={"industries": icp.industries, "min_employees": icp.min_employees, "max_employees": icp.max_employees, "locations": icp.locations},
            provider="freebuff",
            created_at=_dt(days=25),
        )
        db.add(qual_result)
        db.flush()

        print(f"      📊 Qualification created — score: {qual_data['overall_score']} ({qual_data['priority']})")

        # ── Outreach Task (for companies with outreach data) ─────────────
        outreach_data_list = [o for o in OUTREACH_DATA if o["company_name"] == company_name]
        if outreach_data_list:
            odata = outreach_data_list[0]
            outreach_task = models.AgentTask(
                id=_id(),
                agent_type="outreach",
                status="waiting_for_approval",
                company_id=company.id,
                lead_id=lead.id,
                input_data={"company_name": company.name, "research_findings": company_data["profile_data"], "qualification": qual_data},
                output_data={"outreach_strategy": {
                    "recommended_channel": odata["strategy_channel"],
                    "urgency": odata["strategy_urgency"],
                    "reasoning": odata["strategy_reasoning"],
                }, "personalization": {
                    "company_hook": odata["company_hook"],
                    "detected_pain_point": odata["detected_pain_point"],
                    "flytbase_value_proposition": odata["flytbase_value_proposition"],
                }, "email_draft": {
                    "subject": odata["draft_subject"],
                    "body": odata["draft_body"],
                    "follow_up_suggestion": odata["follow_up_suggestion"],
                }},
                requires_human_approval=True,
                created_at=_dt(days=24),
                updated_at=_dt(days=24),
            )
            db.add(outreach_task)
            db.flush()

            _add_log(db, outreach_task.id, "outreach_started", "Generating outreach strategy", {"company": company.name}, _dt(days=24, hours=3))
            _add_log(db, outreach_task.id, "strategy_planned", "Outreach strategy planned", {"channel": odata["strategy_channel"]}, _dt(days=24, hours=2))
            _add_log(db, outreach_task.id, "personalization_generated", "Personalization intelligence generated", {}, _dt(days=24, hours=1))
            _add_log(db, outreach_task.id, "email_draft_created", "Email draft created — awaiting human approval", {}, _dt(days=24))
            _add_log(db, outreach_task.id, "task_completed", "Outreach task completed — pending approval", {}, _dt(days=24))

            # Outreach Draft
            draft = models.OutreachDraft(
                id=_id(),
                task_id=outreach_task.id,
                company_id=company.id,
                lead_id=lead.id,
                report_id=report.id,
                qualification_id=qual_result.id,
                strategy_channel=odata["strategy_channel"],
                strategy_urgency=odata["strategy_urgency"],
                strategy_reasoning=odata["strategy_reasoning"],
                company_hook=odata["company_hook"],
                detected_pain_point=odata["detected_pain_point"],
                flytbase_value_proposition=odata["flytbase_value_proposition"],
                draft_subject=odata["draft_subject"],
                draft_body=odata["draft_body"],
                follow_up_suggestion=odata["follow_up_suggestion"],
                status="pending_approval" if company_name in ("SkyGrid Inc.", "DroneFleet Logistics", "AeroVista") else "approved",
                provider="freebuff",
                created_at=_dt(days=24),
            )
            db.add(draft)
            db.flush()
            intelligence = CompanyIntelligenceBriefBuilder().build(
                company_name=company.name,
                research={"industry": company_data["industry"], **company_data["profile_data"]},
                qualification=qual_data,
            )
            db.add(models.CompanyIntelligenceBrief(
                id=_id(),
                outreach_draft_id=draft.id,
                task_id=outreach_task.id,
                company_id=company.id,
                report_id=report.id,
                qualification_id=qual_result.id,
                brief_data=intelligence,
                source=intelligence["source"],
                created_at=_dt(days=24),
            ))

            # For SkyGrid, also approve the draft (to show a completed outreach)
            if company_name == "SkyGrid Inc.":
                draft.status = "approved"
                draft.approved_by = "BDR (Demo)"
                draft.approved_at = _dt(days=22)

                # Create outreach history
                history = models.OutreachHistory(
                    id=_id(),
                    draft_id=draft.id,
                    company_id=company.id,
                    lead_id=lead.id,
                    sent_subject=odata["draft_subject"],
                    sent_body=odata["draft_body"],
                    channel=odata["strategy_channel"],
                    action="draft_approved",
                    approved_by="BDR (Demo)",
                    approved_at=_dt(days=22),
                )
                db.add(history)

                # Mark task as completed
                outreach_task.status = "completed"
                outreach_task.updated_at = _dt(days=22)

            print(f"      ✉️  Outreach draft created — status: {draft.status}")

        # ── Pipeline Status ──────────────────────────────────────────────
        pipeline_status = models.PipelineStatus(
            id=_id(),
            lead_id=lead.id,
            stage=lead_info["status"],
            is_current=True,
            entered_at=_dt(days=lead_info["pipeline_entered_days_ago"]),
            entered_by=lead_info["pipeline_entered_by"],
            reason=lead_info["pipeline_reason"],
            created_at=_dt(days=lead_info["pipeline_entered_days_ago"]),
        )
        db.add(pipeline_status)
        print(f"      🚀 Pipeline status set to '{lead_info['status']}'")

    # ── 4. Create Inbound Messages (for SkyGrid) ──────────────────────
    skygrid = db.query(models.Company).filter(models.Company.name == "SkyGrid Inc.").first()
    if skygrid:
        for i, msg_data in enumerate(INBOUND_MESSAGES):
            existing_msg = db.query(models.InboundMessage).filter(
                models.InboundMessage.from_email == msg_data["from_email"],
                models.InboundMessage.subject == msg_data["subject"],
            ).first()
            if existing_msg:
                print(f"   ℹ️  Inbound message '{msg_data['subject'][:40]}...' already exists, skipping")
                continue

            inbound_task = models.AgentTask(
                id=_id(),
                agent_type="inbound",
                status="completed" if i == 0 else ("waiting_for_approval" if i == 1 else "waiting_for_approval"),
                company_id=skygrid.id,
                lead_id=db.query(models.Lead).filter(models.Lead.company_id == skygrid.id).first().id,
                input_data={"message": {
                    "from_email": msg_data["from_email"],
                    "from_name": msg_data["from_name"],
                    "subject": msg_data["subject"],
                    "body": msg_data["body"],
                }},
                requires_human_approval=i > 0,
                created_at=_dt(days=22 - i * 2),
                updated_at=_dt(days=22 - i * 2),
            )
            db.add(inbound_task)
            db.flush()

            # Inbound Message
            inbound_msg = models.InboundMessage(
                id=_id(),
                task_id=inbound_task.id,
                from_email=msg_data["from_email"],
                from_name=msg_data["from_name"],
                subject=msg_data["subject"],
                body=msg_data["body"],
                channel="email",
                intent=msg_data["intent"],
                sentiment=msg_data["sentiment"],
                urgency=msg_data["urgency"],
                lead_action=msg_data["lead_action"],
                status="approved" if i == 0 else "pending_review",
                suggested_reply_subject=f"Re: {msg_data['subject']}",
                suggested_reply_body=msg_data["suggested_reply_body"],
                received_at=_dt(days=22 - i * 2),
                created_at=_dt(days=22 - i * 2),
            )
            db.add(inbound_msg)

            if i == 0:
                inbound_msg.reviewed_by = "BDR (Auto-approved)"
                inbound_msg.reviewed_at = _dt(days=21)

            _add_log(db, inbound_task.id, "inbound_started", "Processing inbound message", {"from": msg_data["from_email"]}, _dt(days=22 - i * 2, hours=1))
            _add_log(db, inbound_task.id, "intent_classified", f"Intent classified as {msg_data['intent']}", {"intent": msg_data["intent"], "confidence": 0.92}, _dt(days=22 - i * 2))
            _add_log(db, inbound_task.id, "reply_generated", "Suggested reply generated", {}, _dt(days=22 - i * 2))
            _add_log(db, inbound_task.id, "task_completed", "Inbound task completed", {}, _dt(days=22 - i * 2))

            print(f"      📨 Inbound message created from {msg_data['from_name']} — intent: {msg_data['intent']}")

    # ── 5. Create Conversations for SkyGrid (demo history) ────────────
    skygrid_lead = db.query(models.Lead).filter(models.Lead.company_id == skygrid.id).first()
    if skygrid_lead:
        existing_convos = db.query(models.Conversation).filter(
            models.Conversation.lead_id == skygrid_lead.id
        ).count()
        if existing_convos == 0:
            conversation = models.Conversation(
                id=_id(),
                company_id=skygrid.id,
                lead_id=skygrid_lead.id,
                contact_id=db.query(models.Contact).filter(models.Contact.company_id == skygrid.id).first().id,
                direction="inbound",
                channel="email",
                subject="Re: Scaling SkyGrid's drone fleet operations",
                body=INBOUND_MESSAGES[0]["body"],
                occurred_at=_dt(days=22),
            )
            db.add(conversation)
            print("      💬 Conversation record created")

    db.commit()
    db.close()

    print("\n✨  Seed complete! Here's what was created:")
    print("   5 companies with complete lifecycle data")
    print("   Research reports + qualification scores for all")
    print("   Outreach drafts (3 pending approval, 1 approved)")
    print("   3 inbound messages from SkyGrid (1 approved, 2 pending)")
    print("   Pipeline positions across 5 stages")
    print("   Activity logs for all agent tasks")
    print("\n   ▶️  Start the server and visit http://localhost:8000")
    print()


def _add_log(
    db: SessionLocal,
    task_id: uuid.UUID,
    event_type: str,
    message: str,
    data: dict | None = None,
    created_at: datetime | None = None,
) -> None:
    """Add an agent log entry."""
    log = models.AgentLog(
        id=_id(),
        task_id=task_id,
        level="info" if event_type != "error" else "error",
        event_type=event_type,
        message=message,
        data=data or {},
        created_at=created_at or _now,
    )
    db.add(log)


if __name__ == "__main__":
    seed_database()
