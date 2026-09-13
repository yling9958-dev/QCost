EXTENSION = qmap_benchmark
MODULE_big = qmap_benchmark
OBJS = qmap_benchmark.o
DATA = qmap_benchmark--1.0.sql
PG_CONFIG ?= pg_config
QMAP_PROJECT_ROOT ?= $(abspath ../..)
QMAP_CPP_BUILD_ROOT ?= $(HOME)/.cache/qmap-li-posix/build/current
QMAP_RUNTIME_INSTALL_DIR ?= $(shell $(PG_CONFIG) --pkglibdir)
PG_CPPFLAGS += -I"$(QMAP_PROJECT_ROOT)/cpp/include"
SHLIB_LINK += -L$(QMAP_CPP_BUILD_ROOT)/lib -Wl,-rpath,$(QMAP_RUNTIME_INSTALL_DIR) -lqmap_runtime -lstdc++
CXXFLAGS += -std=c++17
PGXS := $(shell $(PG_CONFIG) --pgxs)
include $(PGXS)
