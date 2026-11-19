"""Automatic model discovery, generation tracking and lifecycle management.

One pipeline (sources -> observations -> merge -> classification -> verification ->
retention -> atomic publication) produces the single authoritative catalogue. Nothing in
this package needs an inference credential: discovery, comparison and redirection are
independent of whether AI Compass can *execute* a model.
"""
