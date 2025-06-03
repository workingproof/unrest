

CREATE TABLE users (
    id text default (uuid_generate_v4())::text not null,
    email text not null,
    apikey text,
    claims jsonb default '{}'::jsonb   
);

INSERT INTO users (email, claims, apikey) VALUES
    ('foo@example.com', '{"support": false, "developer": false, "admin": true}'::jsonb, 'secretapikey123'),
    ('bar@example.com', '{"support": true}'::jsonb, 'secretapikey456'),
    ('abc@example.com', '{"developer": true}'::jsonb, NULL),
    ('def@example.com', '{"support": true}'::jsonb, NULL),
    ('ghi@example.com', '{"support": true}'::jsonb, NULL),
    ('lmn@example.com', '{"developer": true}'::jsonb, NULL),
    ('opq@example.com', '{"developer": true}'::jsonb, NULL),
    ('rst@example.com', '{"admin": true}'::jsonb, NULL),
    ('uvw@example.com', '{"developer": true}'::jsonb, NULL);

