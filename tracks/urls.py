"""
URL Configuration for the Tracks Django app in Ensembl Track API endpoint

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.1/topics/http/urls/
"""
from django.urls import path
from . import views

app_name = "tracks"

urlpatterns = [
    path("<slug:genome_id>", views.genome_tracks, name="genome_tracks"),
]