"""Domain / vertical specs.

Each domain ships with a page-vocabulary of 10 distinct page-types; the
brand spec samples PAGES_PER_SITE_RANGE pages from this list (always
including the home/landing-equivalent first). Domain provides the content
shape; archetype provides the layout grammar; aesthetic provides the
visual style.

15 domains. Smoke wave samples 5 of these.
"""
from __future__ import annotations

from typing import TypedDict


class Domain(TypedDict):
    name: str
    label: str             # human-readable
    industry: str          # NAICS-like
    page_vocabulary: list[dict]  # 10 entries: {"slug": "...", "title": "...", "purpose": "..."}


DOMAINS: list[Domain] = [
    {
        "name": "healthcare-emr",
        "label": "Healthcare EMR / clinic management",
        "industry": "Ambulatory Health Care",
        "page_vocabulary": [
            {"slug": "patient-dashboard", "title": "Patient Dashboard", "purpose": "overview of one patient's recent visits, vitals, alerts"},
            {"slug": "appointment-calendar", "title": "Appointment Calendar", "purpose": "weekly/monthly calendar grid showing scheduled appointments"},
            {"slug": "staff-management", "title": "Staff & Providers", "purpose": "directory of clinical staff with roles, availability, contact"},
            {"slug": "ehr-record", "title": "Electronic Health Record", "purpose": "single patient's chart: history, diagnoses, medications, notes"},
            {"slug": "prescriptions", "title": "Prescriptions", "purpose": "active medications, refills, prescription history"},
            {"slug": "lab-results", "title": "Lab Results", "purpose": "list of recent lab tests with values, ranges, flagged abnormals"},
            {"slug": "billing-insurance", "title": "Billing & Insurance", "purpose": "invoices, claims status, insurance coverage details"},
            {"slug": "financing-plans", "title": "Payment Plans", "purpose": "installment options, balance, payment history"},
            {"slug": "messaging", "title": "Patient Messages", "purpose": "inbox of patient-provider messages with thread view"},
            {"slug": "settings", "title": "Practice Settings", "purpose": "clinic profile, integrations, notification preferences"},
        ],
    },
    {
        "name": "fintech-banking",
        "label": "Personal banking app",
        "industry": "Financial Services",
        "page_vocabulary": [
            {"slug": "account-overview", "title": "Accounts", "purpose": "list of accounts with balances, recent activity"},
            {"slug": "transactions", "title": "Transactions", "purpose": "filterable transaction list with categories, search"},
            {"slug": "transfers", "title": "Transfers", "purpose": "send money — recipient picker, amount, schedule"},
            {"slug": "cards", "title": "Cards", "purpose": "manage debit/credit cards: freeze, limits, virtual cards"},
            {"slug": "statements", "title": "Statements", "purpose": "monthly statements list, downloadable"},
            {"slug": "budgets", "title": "Budgets", "purpose": "spending categories with progress bars vs budget"},
            {"slug": "investments", "title": "Investments", "purpose": "portfolio holdings, performance, allocation chart"},
            {"slug": "recipients", "title": "Payees", "purpose": "saved payment recipients with account details"},
            {"slug": "security", "title": "Security", "purpose": "2FA, device list, login history, password reset"},
            {"slug": "support", "title": "Help & Support", "purpose": "FAQ, contact channels, ticket history"},
        ],
    },
    {
        "name": "restaurant-ops",
        "label": "Restaurant operations / POS console",
        "industry": "Food Services",
        "page_vocabulary": [
            {"slug": "live-orders", "title": "Live Orders", "purpose": "active tickets grouped by status: new, cooking, ready"},
            {"slug": "table-map", "title": "Floor Plan", "purpose": "visual floor plan with tables, status (open/seated/dirty)"},
            {"slug": "menu", "title": "Menu Manager", "purpose": "menu items by category, prices, availability toggles"},
            {"slug": "staff-schedule", "title": "Staff Schedule", "purpose": "weekly shift schedule grid with assigned staff"},
            {"slug": "inventory", "title": "Inventory", "purpose": "stock levels, low-stock alerts, par levels"},
            {"slug": "reservations", "title": "Reservations", "purpose": "upcoming reservations list with party size, time, notes"},
            {"slug": "customers", "title": "Customer CRM", "purpose": "regulars list with visit history, preferences, tags"},
            {"slug": "sales-reports", "title": "Sales Reports", "purpose": "daily/weekly revenue, top items, charts"},
            {"slug": "discounts", "title": "Promotions", "purpose": "active discount codes, scheduled promos"},
            {"slug": "settings", "title": "Restaurant Settings", "purpose": "hours, payment integrations, printer config"},
        ],
    },
    {
        "name": "legal-practice",
        "label": "Legal practice management",
        "industry": "Legal Services",
        "page_vocabulary": [
            {"slug": "cases-dashboard", "title": "Cases", "purpose": "list of open matters with status, deadlines, assigned attorney"},
            {"slug": "client-roster", "title": "Clients", "purpose": "client directory with contact, billing status"},
            {"slug": "matter-detail", "title": "Matter Detail", "purpose": "single case: parties, timeline, documents, billing"},
            {"slug": "document-library", "title": "Documents", "purpose": "searchable document repository with tags, versions"},
            {"slug": "billable-hours", "title": "Time Entries", "purpose": "log of billable time with client, matter, description"},
            {"slug": "invoices", "title": "Invoices", "purpose": "draft and sent invoices with status, totals"},
            {"slug": "calendar", "title": "Calendar", "purpose": "deadlines, court dates, meetings — calendar view"},
            {"slug": "contacts", "title": "Contacts", "purpose": "people directory: counsel, experts, witnesses"},
            {"slug": "reports", "title": "Reports", "purpose": "matter aging, realization rates, attorney productivity"},
            {"slug": "settings", "title": "Firm Settings", "purpose": "users, billing rates, document templates"},
        ],
    },
    {
        "name": "education-lms",
        "label": "Learning management system",
        "industry": "Educational Services",
        "page_vocabulary": [
            {"slug": "course-catalog", "title": "Course Catalog", "purpose": "browsable course grid with categories, ratings"},
            {"slug": "course-player", "title": "Course Player", "purpose": "lesson video + transcript + module navigation"},
            {"slug": "gradebook", "title": "Gradebook", "purpose": "table of students × assignments with scores"},
            {"slug": "assignments", "title": "Assignments", "purpose": "list of assignments with due dates, submission status"},
            {"slug": "enrollment", "title": "Enrollment", "purpose": "students enrolled per course with progress bars"},
            {"slug": "student-profile", "title": "Student Profile", "purpose": "single student: courses, grades, attendance"},
            {"slug": "announcements", "title": "Announcements", "purpose": "course announcements feed with reply threads"},
            {"slug": "calendar", "title": "Calendar", "purpose": "due dates, classes, exams — monthly view"},
            {"slug": "library", "title": "Resource Library", "purpose": "searchable reading materials, videos, slides"},
            {"slug": "admin", "title": "Admin Console", "purpose": "users, courses, system configuration"},
        ],
    },
    {
        "name": "real-estate-crm",
        "label": "Real estate CRM",
        "industry": "Real Estate",
        "page_vocabulary": [
            {"slug": "listings", "title": "Listings", "purpose": "card grid of active property listings with photos, price"},
            {"slug": "listing-detail", "title": "Listing Detail", "purpose": "single property: gallery, specs, agent, offers"},
            {"slug": "leads", "title": "Leads", "purpose": "pipeline view of buyer/seller leads by stage"},
            {"slug": "deals", "title": "Deals Pipeline", "purpose": "kanban of deals: showing, offer, contract, closed"},
            {"slug": "agents", "title": "Agents", "purpose": "agent directory with stats, listings, commissions"},
            {"slug": "open-houses", "title": "Open Houses", "purpose": "scheduled open houses with RSVPs"},
            {"slug": "documents", "title": "Documents", "purpose": "transaction docs: contracts, disclosures, by listing"},
            {"slug": "calendar", "title": "Calendar", "purpose": "showings, closings, agent calendar"},
            {"slug": "reports", "title": "Market Reports", "purpose": "market trends, agent performance, charts"},
            {"slug": "settings", "title": "Settings", "purpose": "brokerage profile, integrations, MLS connections"},
        ],
    },
    {
        "name": "ecommerce-admin",
        "label": "E-commerce admin / Shopify-like",
        "industry": "Retail Trade",
        "page_vocabulary": [
            {"slug": "orders", "title": "Orders", "purpose": "order list with status, customer, fulfillment"},
            {"slug": "products", "title": "Products", "purpose": "product catalog grid with inventory, status"},
            {"slug": "inventory", "title": "Inventory", "purpose": "stock levels by SKU and location"},
            {"slug": "customers", "title": "Customers", "purpose": "customer directory with order history, LTV"},
            {"slug": "discounts", "title": "Discounts", "purpose": "active discount codes, performance"},
            {"slug": "analytics", "title": "Analytics", "purpose": "revenue, conversion, top products — charts"},
            {"slug": "shipping", "title": "Shipping", "purpose": "shipping zones, rates, carriers"},
            {"slug": "marketing", "title": "Marketing", "purpose": "campaigns, email lists, automations"},
            {"slug": "settings", "title": "Store Settings", "purpose": "store info, taxes, payment providers"},
            {"slug": "integrations", "title": "Apps & Integrations", "purpose": "installed apps, integration marketplace"},
        ],
    },
    {
        "name": "logistics-freight",
        "label": "Logistics / freight dispatch",
        "industry": "Transportation",
        "page_vocabulary": [
            {"slug": "shipments", "title": "Shipments", "purpose": "active shipments list with origin, destination, ETA"},
            {"slug": "fleet", "title": "Fleet", "purpose": "vehicle list with status, location, driver"},
            {"slug": "drivers", "title": "Drivers", "purpose": "driver roster with hours, certifications, scores"},
            {"slug": "dispatch-board", "title": "Dispatch Board", "purpose": "live map + load assignment kanban"},
            {"slug": "routes", "title": "Routes", "purpose": "saved routes with avg time, mileage"},
            {"slug": "customers", "title": "Customers", "purpose": "shipper accounts, contract rates"},
            {"slug": "invoicing", "title": "Invoicing", "purpose": "freight invoices with statuses"},
            {"slug": "fuel", "title": "Fuel & Maintenance", "purpose": "fuel log, scheduled maintenance"},
            {"slug": "compliance", "title": "Compliance", "purpose": "DOT logs, inspections, violations"},
            {"slug": "settings", "title": "Settings", "purpose": "company profile, integrations, alerts"},
        ],
    },
    {
        "name": "devops-platform",
        "label": "Developer / DevOps platform",
        "industry": "Software",
        "page_vocabulary": [
            {"slug": "projects", "title": "Projects", "purpose": "list of projects with status, last deploy, owners"},
            {"slug": "builds", "title": "Builds", "purpose": "CI build history with status, duration, trigger"},
            {"slug": "deploys", "title": "Deployments", "purpose": "deployment timeline by environment"},
            {"slug": "environments", "title": "Environments", "purpose": "env list: prod, staging, preview — with versions"},
            {"slug": "logs", "title": "Logs", "purpose": "streaming logs with filter, search, level"},
            {"slug": "alerts", "title": "Alerts", "purpose": "incident list with severity, owner, status"},
            {"slug": "team", "title": "Team", "purpose": "members directory with roles, on-call rotation"},
            {"slug": "billing", "title": "Billing", "purpose": "usage charts, plan, invoices"},
            {"slug": "integrations", "title": "Integrations", "purpose": "connected services: GitHub, Slack, PagerDuty"},
            {"slug": "settings", "title": "Settings", "purpose": "org profile, SSO, API tokens"},
        ],
    },
    {
        "name": "hr-payroll",
        "label": "HR / payroll system",
        "industry": "Management of Companies",
        "page_vocabulary": [
            {"slug": "people-directory", "title": "People", "purpose": "employee directory cards with photo, role, dept"},
            {"slug": "org-chart", "title": "Org Chart", "purpose": "hierarchical tree of org structure"},
            {"slug": "time-off", "title": "Time Off", "purpose": "leave balances, pending requests, calendar"},
            {"slug": "pay-runs", "title": "Pay Runs", "purpose": "pay period table with totals, status"},
            {"slug": "benefits", "title": "Benefits", "purpose": "enrolled benefits, open enrollment"},
            {"slug": "reviews", "title": "Performance Reviews", "purpose": "review cycle table with ratings, status"},
            {"slug": "hiring", "title": "Hiring Pipeline", "purpose": "candidates kanban by stage"},
            {"slug": "onboarding", "title": "Onboarding", "purpose": "new-hire checklist, progress per employee"},
            {"slug": "expenses", "title": "Expenses", "purpose": "expense reports list, approvals"},
            {"slug": "settings", "title": "Company Settings", "purpose": "company profile, holidays, policies"},
        ],
    },
    # 5 more domains kept short for smoke wave; expand later
    {
        "name": "travel-booking",
        "label": "Travel / hospitality booking",
        "industry": "Accommodation",
        "page_vocabulary": [
            {"slug": "properties", "title": "Properties", "purpose": "property cards with thumbnails, location, rate"},
            {"slug": "property-detail", "title": "Property", "purpose": "single property gallery, amenities, calendar"},
            {"slug": "reservations", "title": "Reservations", "purpose": "calendar of bookings across properties"},
            {"slug": "guests", "title": "Guests", "purpose": "guest list with visit history"},
            {"slug": "channels", "title": "Channels", "purpose": "OTA connections — Airbnb, Booking, etc."},
            {"slug": "rates", "title": "Rates & Availability", "purpose": "calendar of nightly rates, restrictions"},
            {"slug": "housekeeping", "title": "Housekeeping", "purpose": "cleaning schedule by unit"},
            {"slug": "reports", "title": "Reports", "purpose": "occupancy, ADR, RevPAR charts"},
            {"slug": "messaging", "title": "Guest Messages", "purpose": "inbox of guest conversations"},
            {"slug": "settings", "title": "Settings", "purpose": "host profile, integrations"},
        ],
    },
    {
        "name": "gov-services",
        "label": "Government / civic services portal",
        "industry": "Public Administration",
        "page_vocabulary": [
            {"slug": "service-catalog", "title": "Services", "purpose": "browsable services with categories, search"},
            {"slug": "application", "title": "Apply", "purpose": "multi-step application form with progress"},
            {"slug": "status-tracker", "title": "Application Status", "purpose": "timeline view of application progress"},
            {"slug": "payments", "title": "Payments", "purpose": "fees due, payment history"},
            {"slug": "documents", "title": "My Documents", "purpose": "uploaded forms, certificates"},
            {"slug": "faq", "title": "Help Center", "purpose": "FAQ sections, contact info"},
            {"slug": "appointments", "title": "Appointments", "purpose": "in-person appointment scheduling"},
            {"slug": "account", "title": "My Account", "purpose": "personal info, dependents, verification status"},
            {"slug": "notifications", "title": "Notifications", "purpose": "list of system messages and updates"},
            {"slug": "accessibility", "title": "Accessibility", "purpose": "accessibility statement, alternate formats"},
        ],
    },
    {
        "name": "marketing-cms",
        "label": "Marketing site builder / CMS",
        "industry": "Software",
        "page_vocabulary": [
            {"slug": "site-overview", "title": "Site Overview", "purpose": "dashboard: pages, visits, top pages"},
            {"slug": "pages-editor", "title": "Pages", "purpose": "list of pages with status, edit controls"},
            {"slug": "content-library", "title": "Content Library", "purpose": "media, copy snippets, components"},
            {"slug": "seo", "title": "SEO", "purpose": "page-level SEO scores, keywords"},
            {"slug": "campaigns", "title": "Campaigns", "purpose": "marketing campaigns with performance"},
            {"slug": "forms", "title": "Forms", "purpose": "lead forms with submissions"},
            {"slug": "analytics", "title": "Analytics", "purpose": "traffic, conversions, charts"},
            {"slug": "integrations", "title": "Integrations", "purpose": "third-party integrations"},
            {"slug": "team", "title": "Team", "purpose": "users with roles, permissions"},
            {"slug": "settings", "title": "Settings", "purpose": "domain, billing, branding"},
        ],
    },
    {
        "name": "nonprofit-donations",
        "label": "Nonprofit / donations platform",
        "industry": "Nonprofit",
        "page_vocabulary": [
            {"slug": "cause-overview", "title": "Cause", "purpose": "mission, impact metrics, hero stat cards"},
            {"slug": "projects", "title": "Projects", "purpose": "active projects with progress, goals"},
            {"slug": "donate", "title": "Donate", "purpose": "donation flow — amount, frequency, payment"},
            {"slug": "donor-dashboard", "title": "Donor Dashboard", "purpose": "donor's giving history, recurring donations"},
            {"slug": "events", "title": "Events", "purpose": "upcoming fundraising events, RSVP"},
            {"slug": "volunteers", "title": "Volunteers", "purpose": "volunteer opportunities list"},
            {"slug": "impact", "title": "Impact Reports", "purpose": "annual report with charts, stories"},
            {"slug": "blog", "title": "Updates", "purpose": "post list with featured story"},
            {"slug": "contact", "title": "Contact", "purpose": "contact form, office locations"},
            {"slug": "about", "title": "About", "purpose": "team, board, mission"},
        ],
    },
    {
        "name": "conference-event",
        "label": "Conference / event platform",
        "industry": "Events",
        "page_vocabulary": [
            {"slug": "schedule", "title": "Schedule", "purpose": "multi-day timeline of sessions"},
            {"slug": "speakers", "title": "Speakers", "purpose": "speaker grid with photos, bios"},
            {"slug": "session-detail", "title": "Session", "purpose": "single session: speakers, abstract, room"},
            {"slug": "attendees", "title": "Attendees", "purpose": "attendee directory (opt-in)"},
            {"slug": "sponsors", "title": "Sponsors", "purpose": "sponsor logos by tier, links"},
            {"slug": "registration", "title": "Register", "purpose": "ticket selection, checkout"},
            {"slug": "my-agenda", "title": "My Agenda", "purpose": "user's saved sessions, calendar view"},
            {"slug": "venue", "title": "Venue", "purpose": "venue map, directions, accommodations"},
            {"slug": "livestream", "title": "Livestream", "purpose": "current session video + chat sidebar"},
            {"slug": "settings", "title": "Settings", "purpose": "user profile, notifications"},
        ],
    },
]


def sample_domain(rng) -> Domain:
    return rng.choice(DOMAINS)


def get_domain_by_name(name: str) -> Domain:
    for d in DOMAINS:
        if d["name"] == name:
            return d
    raise KeyError(f"unknown domain: {name}")


def sample_page_list(rng, domain: Domain, n_pages: int) -> list[dict]:
    """Sample `n_pages` from the domain's vocabulary, always including the
    first page (typically the most-load-bearing dashboard/home/listings).
    """
    vocab = domain["page_vocabulary"]
    if n_pages >= len(vocab):
        return list(vocab)
    first = vocab[0]
    rest = list(vocab[1:])
    rng.shuffle(rest)
    return [first] + rest[: n_pages - 1]
