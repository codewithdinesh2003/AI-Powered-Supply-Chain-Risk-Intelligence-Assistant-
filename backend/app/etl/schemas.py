"""Canonical supply chain schema definition and transform type constants."""
from __future__ import annotations

from typing import Any, Dict

# ── Known column aliases for Layer-1 exact matching ──────────────────────────
# Each list contains every known lowercase/stripped variant for that canonical field.

KNOWN_ALIASES: Dict[str, list] = {
    "supplier_id": [
        "supplier_id", "supplierid", "supplier id", "supplier_code", "suppliercode",
        "vendor_id", "vendorid", "vendor id", "vendor_code", "supplier ref",
        "supplier_ref", "supplierref",
    ],
    "supplier_name": [
        "supplier_name", "suppliername", "supplier name", "supplier",
        "vendor_name", "vendorname", "vendor name", "vendor",
        "company_name", "company name",
    ],
    "product_type": [
        "product_type", "producttype", "product type", "category",
        "product_category", "productcategory", "product category",
        "item_type", "itemtype", "item type", "product class",
    ],
    "sku": [
        "sku", "item_sku", "itemsku", "product_sku", "productsku",
        "sku_id", "skuid", "item_code", "itemcode", "product_code", "productcode",
        "item_id", "itemid", "product_id", "productid", "incident_code", "incidentcode",
    ],
    "inventory_level": [
        "inventory_level", "inventorylevel", "inventory level",
        "stock_levels", "stock levels", "stock_level", "stock level",
        "stock", "inventory", "current_stock", "currentstock",
        "stock_quantity", "stockquantity", "quantity_on_hand", "quantityonhand",
        "available_stock", "availablestock",
    ],
    "order_quantity": [
        "order_quantity", "orderquantity", "order quantity",
        "order_quantities", "orderquantities", "order quantities",
        "qty_ordered", "qtyordered", "quantity_ordered", "quantityordered",
        "order_qty", "orderqty",
    ],
    "demand_forecast": [
        "demand_forecast", "demandforecast", "demand forecast",
        "number_of_products_sold", "number of products sold",
        "products_sold", "productssold", "sales", "units_sold", "unitssold",
        "demand", "forecasted_demand", "forecasteddemand", "forecast",
    ],
    "lead_time_days": [
        "lead_time_days", "leadtimedays", "lead time days",
        "lead_time", "leadtime", "lead time",
        "lead_time_(days)", "lead time (days)",
    ],
    "delivery_delay_days": [
        "delivery_delay_days", "deliverydelaydays", "delivery delay days",
        "delivery_delay", "deliverydelay", "delivery delay",
        "delay_days", "delaydays", "delay", "days_delayed", "daysdelayed",
        "shipping_time", "shippingtime", "shipping time",
    ],
    "shipment_status": [
        "shipment_status", "shipmentstatus", "shipment status",
        "shipping_status", "shippingstatus", "shipping status",
        "delivery_status", "deliverystatus", "delivery status",
        "order_status", "orderstatus", "order status",
    ],
    "shipping_carrier": [
        "shipping_carrier", "shippingcarrier", "shipping carrier",
        "shipping_carriers", "shippingcarriers", "shipping carriers",
        "carrier", "carriers", "logistics_provider", "logisticsprovider",
    ],
    "transportation_mode": [
        "transportation_mode", "transportationmode", "transportation mode",
        "transportation_modes", "transportationmodes", "transportation modes",
        "mode", "shipping_mode", "shippingmode", "transport_mode", "transportmode",
        "transport_type", "transporttype",
    ],
    "route": [
        "route", "routes", "shipping_route", "shippingroute",
        "delivery_route", "deliveryroute", "route_id", "routeid",
    ],
    "warehouse_location": [
        "warehouse_location", "warehouselocation", "warehouse location",
        "location", "warehouse", "facility", "storage_location", "storagelocation",
        "storage location", "depot", "distribution_center", "distributioncenter",
    ],
    "transportation_cost": [
        "transportation_cost", "transportationcost", "transportation cost",
        "shipping_costs", "shippingcosts", "shipping costs",
        "shipping_cost", "shippingcost", "shipping cost",
        "freight_cost", "freightcost", "freight cost",
        "logistics_cost", "logisticscost", "delivery_cost", "deliverycost",
    ],
    "manufacturing_cost": [
        "manufacturing_cost", "manufacturingcost", "manufacturing cost",
        "manufacturing_costs", "manufacturingcosts", "manufacturing costs",
        "production_cost", "productioncost", "production cost",
        "cost_to_manufacture", "costtomanufacture", "unit_cost", "unitcost",
    ],
    "revenue": [
        "revenue", "revenue_generated", "revenuegenerated", "revenue generated",
        "sales_revenue", "salesrevenue", "total_revenue", "totalrevenue",
        "gross_revenue", "grossrevenue",
    ],
    "defect_rate": [
        "defect_rate", "defectrate", "defect rate",
        "defect_rates", "defectrates", "defect rates",
        "defects", "defect_ratio", "defectratio",
        "quality_rate", "qualityrate", "failure_rate", "failurerate",
        "rejection_rate", "rejectionrate",
    ],
    "inspection_status": [
        "inspection_status", "inspectionstatus", "inspection status",
        "inspection_results", "inspectionresults", "inspection results",
        "quality_check", "qualitycheck", "inspection_result", "inspectionresult",
    ],
    "production_volume": [
        "production_volume", "productionvolume", "production volume",
        "production_volumes", "productionvolumes", "production volumes",
        "volume", "units_produced", "unitsproduced", "output", "manufactured_qty",
    ],
    "severity": [
        "severity", "risk_severity", "riskseverity", "risk_level", "risklevel",
        "priority", "criticality", "alert_level", "alertlevel",
    ],
    "risk_score": [
        "risk_score", "riskscore", "risk score",
        "impact_score", "impactscore", "impact score",
        "risk_rating", "riskrating", "risk_index", "riskindex",
    ],
    "timestamp": [
        "timestamp", "date", "occurred_at", "occurredat", "occurred at",
        "created_at", "createdat", "event_date", "eventdate",
        "order_date", "orderdate", "transaction_date", "transactiondate",
        "delivery_date", "deliverydate", "record_date", "recorddate", "time",
    ],
}

# Pre-computed flat lookup: normalised_alias → canonical_field (O(1) Layer-1 lookup)
import re as _re


def _norm(s: str) -> str:
    return _re.sub(r"[\s_\-]+", " ", s.lower().strip())


_ALIAS_LOOKUP: Dict[str, str] = {
    _norm(alias): canonical
    for canonical, aliases in KNOWN_ALIASES.items()
    for alias in aliases
}

# ── Transform types ───────────────────────────────────────────────────────────

TRANSFORM_DIRECT       = "direct"
TRANSFORM_DERIVE       = "derive"
TRANSFORM_DIVIDE_100   = "divide_by_100"
TRANSFORM_NEGATE       = "negate"
TRANSFORM_DATE_PARSE   = "date_parse"
TRANSFORM_SLUGIFY      = "slugify"

# ── Canonical schema ──────────────────────────────────────────────────────────

CANONICAL_FIELDS: Dict[str, Dict[str, Any]] = {
    "supplier_id":         {"type": "str",   "required": True,  "description": "Unique supplier identifier"},
    "supplier_name":       {"type": "str",   "required": False, "description": "Supplier display name"},
    "product_type":        {"type": "str",   "required": False, "description": "Product / component category"},
    "sku":                 {"type": "str",   "required": False, "description": "Stock Keeping Unit code"},
    "inventory_level":     {"type": "float", "required": True,  "description": "Current stock quantity (units)"},
    "order_quantity":      {"type": "float", "required": False, "description": "Quantity ordered in this period"},
    "demand_forecast":     {"type": "float", "required": True,  "description": "Forecasted demand (units)"},
    "lead_time_days":      {"type": "float", "required": False, "description": "Supplier quoted lead time in days"},
    "delivery_delay_days": {"type": "float", "required": False, "description": "Actual delay vs expected (derived if absent)"},
    "shipment_status":     {"type": "str",   "required": False, "description": "on_time / delayed / critical / pending (derived)"},
    "shipping_carrier":    {"type": "str",   "required": False, "description": "Carrier or shipping company name"},
    "transportation_mode": {"type": "str",   "required": False, "description": "Road / Air / Rail / Sea"},
    "route":               {"type": "str",   "required": False, "description": "Shipment route identifier"},
    "warehouse_location":  {"type": "str",   "required": True,  "description": "Warehouse city / facility"},
    "transportation_cost": {"type": "float", "required": False, "description": "Shipping and logistics cost (USD)"},
    "manufacturing_cost":  {"type": "float", "required": False, "description": "Cost to manufacture (USD)"},
    "revenue":             {"type": "float", "required": False, "description": "Revenue generated (USD)"},
    "defect_rate":         {"type": "float", "required": False, "description": "Quality defect rate, 0–1 scale"},
    "inspection_status":   {"type": "str",   "required": False, "description": "Inspection result: Pass / Fail / Pending"},
    "production_volume":   {"type": "float", "required": False, "description": "Units produced this period"},
    "severity":            {"type": "str",   "required": False, "description": "Derived risk severity: low/medium/high/critical"},
    "risk_score":          {"type": "float", "required": False, "description": "Derived weighted risk score 0–100"},
    "timestamp":           {"type": "str",   "required": False, "description": "ISO 8601 datetime of the event"},
}

REQUIRED_FIELDS = [k for k, v in CANONICAL_FIELDS.items() if v["required"]]

# ── Mapping from canonical → ingestion pipeline column names ─────────────────

CANONICAL_TO_PIPELINE: Dict[str, str] = {
    "supplier_id":         "SupplierID",
    "supplier_name":       "SupplierName",
    "product_type":        "SupplierCategory",
    "sku":                 "IncidentCode",
    "inventory_level":     "InventoryLevel",
    "order_quantity":      "OrderQuantity",
    "demand_forecast":     "DemandForecast",
    "lead_time_days":      "LeadTimeDays",
    "delivery_delay_days": "DeliveryDelayDays",
    "shipment_status":     "ShipmentStatus",
    "shipping_carrier":    "ShippingCarrier",
    "transportation_mode": "TransportationMode",
    "route":               "Route",
    "warehouse_location":  "WarehouseLocation",
    "transportation_cost": "TransportationCost",
    "manufacturing_cost":  "ManufacturingCost",
    "revenue":             "Revenue",
    "defect_rate":         "DefectRate",
    "inspection_status":   "InspectionStatus",
    "production_volume":   "ProductionVolume",
    "severity":            "Severity",
    "risk_score":          "ImpactScore",
    "timestamp":           "OccurredAt",
}

# ── Shipment status thresholds ────────────────────────────────────────────────

def shipment_status_from_delay(delay_days: float) -> str:
    if delay_days > 14:  return "Critical"
    if delay_days > 7:   return "Delayed"
    if delay_days > 0:   return "In-Transit"
    return "On-Time"

# ── Severity thresholds ───────────────────────────────────────────────────────

def severity_from_metrics(delay_days: float, inventory: float, demand: float, defect_rate: float) -> str:
    coverage = inventory / demand if demand > 0 else 1.0
    if defect_rate > 0.10 or delay_days > 14 or coverage < 0.20:
        return "critical"
    if defect_rate > 0.05 or delay_days > 7 or coverage < 0.50:
        return "high"
    if defect_rate > 0.02 or delay_days > 3 or coverage < 0.70:
        return "medium"
    return "low"

# ── Risk score formula ────────────────────────────────────────────────────────

def risk_score_from_metrics(delay_days: float, inventory: float, demand: float,
                             defect_rate: float, transport_cost: float,
                             avg_transport_cost: float) -> float:
    delay_score     = min(delay_days / 20.0, 1.0)
    coverage        = inventory / demand if demand > 0 else 1.0
    inventory_score = max(0.0, 1.0 - coverage)
    defect_score    = min(defect_rate / 0.15, 1.0)
    cost_ratio      = transport_cost / avg_transport_cost if avg_transport_cost > 0 else 1.0
    cost_score      = min(max(cost_ratio - 1.0, 0.0) / 2.0, 1.0)

    return round(
        (delay_score * 0.35 + inventory_score * 0.25 + defect_score * 0.20 + cost_score * 0.20) * 100,
        2
    )
