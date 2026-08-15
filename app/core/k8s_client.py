from kubernetes import client, config
from kubernetes.client.rest import ApiException


def load_kube_config():
    config.load_kube_config()


def get_core_v1_api() -> client.CoreV1Api:
    load_kube_config()
    return client.CoreV1Api()


def create_namespace(name: str, labels: dict = None):
    api = get_core_v1_api()

    body = client.V1Namespace(
        metadata=client.V1ObjectMeta(
            name=name,
            labels=labels or {}
        )
    )

    try:
        api.create_namespace(body=body)
        return {"status": "created", "namespace": name}
    except ApiException as e:
        if e.status == 409:
            return {"status": "already_exists", "namespace": name}
        raise


def delete_namespace(name: str):
    api = get_core_v1_api()

    try:
        api.delete_namespace(name=name)
        return {"status": "deleting", "namespace": name}
    except ApiException as e:
        if e.status == 404:
            return {"status": "not_found", "namespace": name}
        raise


def get_namespace_status(name: str):
    api = get_core_v1_api()

    try:
        ns = api.read_namespace(name=name)
        return {"status": ns.status.phase, "namespace": name}
    except ApiException as e:
        if e.status == 404:
            return {"status": "not_found", "namespace": name}
        raise


def namespace_exists(name: str) -> bool:
    result = get_namespace_status(name)
    return result["status"] not in ("not_found",)


def get_apps_v1_api() -> client.AppsV1Api:
    load_kube_config()
    return client.AppsV1Api()


def get_networking_v1_api() -> client.NetworkingV1Api:
    load_kube_config()
    return client.NetworkingV1Api()


def create_app_deployment(namespace: str, name: str = "app", image: str = "nginxdemos/hello", container_port: int = 80, replicas: int = 1):
    """
    Deploys the actual application container for this environment.
    Using nginxdemos/hello as a placeholder app image — shows a live
    hello page + pod hostname, proving the deployment is real and reachable.
    """
    apps_api = get_apps_v1_api()

    container = client.V1Container(
        name=name,
        image=image,
        ports=[client.V1ContainerPort(container_port=container_port)],
    )

    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels={"app": name}),
        spec=client.V1PodSpec(containers=[container]),
    )

    spec = client.V1DeploymentSpec(
        replicas=replicas,
        selector=client.V1LabelSelector(match_labels={"app": name}),
        template=template,
    )

    body = client.V1Deployment(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace),
        spec=spec,
    )

    try:
        apps_api.create_namespaced_deployment(namespace=namespace, body=body)
        return {"status": "created", "deployment": name}
    except ApiException as e:
        if e.status == 409:
            return {"status": "already_exists", "deployment": name}
        raise


def create_app_service(namespace: str, name: str = "app", container_port: int = 80):
    """
    Exposes the app deployment internally inside the cluster,
    so the Ingress has something to route traffic to.
    """
    core_api = get_core_v1_api()

    body = client.V1Service(
        metadata=client.V1ObjectMeta(name=name, namespace=namespace),
        spec=client.V1ServiceSpec(
            selector={"app": name},
            ports=[client.V1ServicePort(port=80, target_port=container_port)],
            type="ClusterIP",
        ),
    )

    try:
        core_api.create_namespaced_service(namespace=namespace, body=body)
        return {"status": "created", "service": name}
    except ApiException as e:
        if e.status == 409:
            return {"status": "already_exists", "service": name}
        raise


def create_app_ingress(namespace: str, env_name: str, service_name: str = "app"):
    """
    Creates path-based routing: http://localhost:8080/<env_name>
    Path-based (not host-based) so no /etc/hosts editing is needed for the demo.
    """
    net_api = get_networking_v1_api()

    path = f"/{env_name}"

    ingress_spec = client.V1IngressSpec(
        ingress_class_name="nginx",
        rules=[
            client.V1IngressRule(
                http=client.V1HTTPIngressRuleValue(
                    paths=[
                        client.V1HTTPIngressPath(
                            path=path,
                            path_type="Prefix",
                            backend=client.V1IngressBackend(
                                service=client.V1IngressServiceBackend(
                                    name=service_name,
                                    port=client.V1ServiceBackendPort(number=80),
                                )
                            ),
                        )
                    ]
                )
            )
        ],
    )

    body = client.V1Ingress(
        metadata=client.V1ObjectMeta(
            name=f"{env_name}-ingress",
            namespace=namespace,
            annotations={
                "nginx.ingress.kubernetes.io/rewrite-target": "/",
            },
        ),
        spec=ingress_spec,
    )

    try:
        net_api.create_namespaced_ingress(namespace=namespace, body=body)
        return {"status": "created", "ingress": f"{env_name}-ingress", "url": f"http://localhost:8080{path}"}
    except ApiException as e:
        if e.status == 409:
            return {"status": "already_exists", "ingress": f"{env_name}-ingress"}
        raise
