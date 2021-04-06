"""
URL Configuration for Ensembl Track API endpoint

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.1/topics/http/urls/
"""
from django.contrib import admin
from django.urls import path, include
from .settings import ADMIN_URL

urlpatterns = [
    path("track_categories/", include("tracks.urls", namespace="tracks")),
    path(f"{ADMIN_URL}/", admin.site.urls),
]
