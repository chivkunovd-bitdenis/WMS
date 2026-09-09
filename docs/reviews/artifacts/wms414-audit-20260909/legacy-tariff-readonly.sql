SELECT service_code, unit, count(*) rows FROM billing_tariff_versions WHERE tenant_id='7b98a8aa-c03c-4649-9677-a645be45c622' GROUP BY service_code,unit ORDER BY service_code,unit;
