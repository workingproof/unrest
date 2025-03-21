

CREATE TABLE users (
    id text default (uuid_generate_v4())::text not null,
    email text not null,
    apikey text,
    claims jsonb default '[]'::jsonb   
);

INSERT INTO users (email, claims, apikey) VALUES
    ('foo@example.com', '["support", "developer", "admin"]'::jsonb, 'secretapikey123'),
    ('bar@example.com', '["developer"]'::jsonb, NULL),
    ('baz@other.com', '["support"]'::jsonb, NULL),
    ('abc@example.com', '["developer"]'::jsonb, NULL),
    ('def@example.com', '["developer"]'::jsonb, NULL),
    ('ghi@example.com', '["developer"]'::jsonb, NULL),
    ('lmn@example.com', '["developer"]'::jsonb, NULL),
    ('opq@example.com', '["developer"]'::jsonb, NULL),
    ('rst@example.com', '["developer"]'::jsonb, NULL),
    ('uvw@example.com', '["developer"]'::jsonb, NULL);

