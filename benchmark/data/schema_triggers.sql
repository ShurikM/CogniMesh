-- Silver table change notification triggers
-- CogniMesh RefreshManager listens on 'silver_changes' channel

CREATE OR REPLACE FUNCTION notify_silver_change() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('silver_changes', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME);
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Trigger on each Silver table (FOR EACH STATEMENT — fires once per operation, not per row)
DROP TRIGGER IF EXISTS silver_customer_profiles_notify ON silver.customer_profiles;
CREATE TRIGGER silver_customer_profiles_notify
    AFTER INSERT OR UPDATE OR DELETE ON silver.customer_profiles
    FOR EACH STATEMENT EXECUTE FUNCTION notify_silver_change();

DROP TRIGGER IF EXISTS silver_product_metrics_notify ON silver.product_metrics;
CREATE TRIGGER silver_product_metrics_notify
    AFTER INSERT OR UPDATE OR DELETE ON silver.product_metrics
    FOR EACH STATEMENT EXECUTE FUNCTION notify_silver_change();

DROP TRIGGER IF EXISTS silver_orders_enriched_notify ON silver.orders_enriched;
CREATE TRIGGER silver_orders_enriched_notify
    AFTER INSERT OR UPDATE OR DELETE ON silver.orders_enriched
    FOR EACH STATEMENT EXECUTE FUNCTION notify_silver_change();
