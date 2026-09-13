CREATE FUNCTION qmap_range_query(
    method_name text,
    xmin double precision,
    ymin double precision,
    xmax double precision,
    ymax double precision
)
RETURNS SETOF bigint
AS 'MODULE_PATHNAME', 'qmap_range_query'
LANGUAGE C STRICT PARALLEL RESTRICTED;

CREATE FUNCTION qmap_reset_index_cache()
RETURNS void
AS 'MODULE_PATHNAME', 'qmap_reset_index_cache'
LANGUAGE C PARALLEL RESTRICTED;

CREATE FUNCTION qmap_range_count(
    method_name text,
    xmin double precision,
    ymin double precision,
    xmax double precision,
    ymax double precision
)
RETURNS bigint
AS 'MODULE_PATHNAME', 'qmap_range_count'
LANGUAGE C STRICT PARALLEL RESTRICTED;

CREATE FUNCTION qmap_preload_index(method_name text)
RETURNS boolean
AS 'MODULE_PATHNAME', 'qmap_preload_index'
LANGUAGE C STRICT PARALLEL RESTRICTED;

CREATE FUNCTION qmap_fairness_counters(method_name text)
RETURNS text
AS 'MODULE_PATHNAME', 'qmap_fairness_counters'
LANGUAGE C STRICT PARALLEL RESTRICTED;

CREATE FUNCTION qmf_range_count(double precision, double precision, double precision, double precision)
RETURNS bigint LANGUAGE SQL STRICT PARALLEL RESTRICTED
AS $$ SELECT qmap_range_count('qmap_uniform_qmf', $1, $2, $3, $4) $$;
CREATE FUNCTION lisa_range_count(double precision, double precision, double precision, double precision)
RETURNS bigint LANGUAGE SQL STRICT PARALLEL RESTRICTED
AS $$ SELECT qmap_range_count('lisa', $1, $2, $3, $4) $$;
CREATE FUNCTION rsmi_range_count(double precision, double precision, double precision, double precision)
RETURNS bigint LANGUAGE SQL STRICT PARALLEL RESTRICTED
AS $$ SELECT qmap_range_count('rsmi', $1, $2, $3, $4) $$;
CREATE FUNCTION flood_range_count(double precision, double precision, double precision, double precision)
RETURNS bigint LANGUAGE SQL STRICT PARALLEL RESTRICTED
AS $$ SELECT qmap_range_count('flood', $1, $2, $3, $4) $$;
CREATE FUNCTION tsunami_range_count(double precision, double precision, double precision, double precision)
RETURNS bigint LANGUAGE SQL STRICT PARALLEL RESTRICTED
AS $$ SELECT qmap_range_count('tsunami', $1, $2, $3, $4) $$;
CREATE FUNCTION lmsfc_range_count(double precision, double precision, double precision, double precision)
RETURNS bigint LANGUAGE SQL STRICT PARALLEL RESTRICTED
AS $$ SELECT qmap_range_count('lmsfc', $1, $2, $3, $4) $$;
CREATE FUNCTION bmtree_range_count(double precision, double precision, double precision, double precision)
RETURNS bigint LANGUAGE SQL STRICT PARALLEL RESTRICTED
AS $$ SELECT qmap_range_count('bmtree', $1, $2, $3, $4) $$;
CREATE FUNCTION qmap_profile_query(text, double precision, double precision, double precision, double precision)
RETURNS text AS 'MODULE_PATHNAME', 'qmap_profile_query' LANGUAGE C STRICT VOLATILE;
