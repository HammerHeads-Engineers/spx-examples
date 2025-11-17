# syntax=docker/dockerfile:1.6

ARG DALIGATEWAY_REPO=https://github.com/henrik-andreasen/DaliGatewayServer.git
ARG DALIGATEWAY_REF=main
ARG DALIGATEWAY_PROJECT=src/DaliGatewayServer/DaliGatewayServer.csproj

FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
ARG DALIGATEWAY_REPO
ARG DALIGATEWAY_REF
ARG DALIGATEWAY_PROJECT
WORKDIR /src
RUN git clone --depth 1 --branch "${DALIGATEWAY_REF}" "${DALIGATEWAY_REPO}" .
RUN dotnet publish "${DALIGATEWAY_PROJECT}" -c Release -o /app/publish

FROM mcr.microsoft.com/dotnet/aspnet:8.0
ENV ASPNETCORE_URLS=http://0.0.0.0:8081 \
    DALIGATEWAY__DATA_DIRECTORY=/data
WORKDIR /app
COPY --from=build /app/publish .
VOLUME ["/data"]
EXPOSE 8081
ENTRYPOINT ["dotnet", "DaliGatewayServer.dll"]
