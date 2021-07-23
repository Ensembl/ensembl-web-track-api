"""
URL Configuration for Ensembl Track API endpoint

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.1/topics/http/urls/
"""
from django.urls import path, include

urlpatterns = [
    path("track_categories/", include("tracks.urls", namespace="tracks")),
]
