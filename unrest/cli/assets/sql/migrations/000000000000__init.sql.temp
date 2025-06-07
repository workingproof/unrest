

CREATE TABLE users (
    user_id uuid default uuid_generate_v4() not null primary key,
    username text not null
);

CREATE TABLE todos (
    created_at timestamp not null default (now() at time zone 'UTC'),
    todo_id uuid default uuid_generate_v4() not null primary key,
    user_id uuid not null,
    description text not null
);

INSERT INTO users (username) VALUES ('foo@example.com')


