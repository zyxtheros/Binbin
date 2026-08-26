-- Seed / default data. Safe to run on every startup — uses ON CONFLICT DO NOTHING.
-- Add whatever default spec fields your app should ship with out of the box.

INSERT INTO spec_field_definitions (field_key, display_name, field_type, unit, unit_system, sort_order) VALUES
    ('mass_kg', 'Mass', 'number', 'kg', 'Metric', 10),
    ('weight_lb', 'Weight', 'number', 'lb', 'Imperial', 20),
    ('length_mm', 'Length', 'number', 'mm', 'Metric', 30),
    ('length_ft', 'Length', 'number', 'ft', 'Imperial', 40),
    ('length_in', 'Length', 'number', 'in.', 'Imperial', 50),
    ('color',  'Color',  'text',  NULL, NULL, 60)
ON CONFLICT (field_key) DO NOTHING;